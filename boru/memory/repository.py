import json
import os
from collections.abc import Sequence
from pathlib import Path
from threading import RLock

from boru.memory.models import (
    MemoryRecord,
)


class JsonMemoryRepository:
    """
    Uzun süreli hafıza kayıtlarını
    atomik JSON yazımıyla saklar.
    """

    def __init__(
        self,
        file_path: str | Path,
    ):
        self._path = Path(
            file_path
        )

        self._lock = RLock()

    def load_all(
        self,
    ) -> list[MemoryRecord]:
        with self._lock:
            if not self._path.exists():
                return []

            try:
                with self._path.open(
                    "r",
                    encoding="utf-8",
                ) as handle:
                    data = json.load(
                        handle
                    )

            except (
                OSError,
                json.JSONDecodeError,
            ) as error:
                raise RuntimeError(
                    (
                        "Uzun süreli "
                        "hafıza okunamadı: "
                        f"{self._path}"
                    )
                ) from error

            if not isinstance(
                data,
                list,
            ):
                raise RuntimeError(
                    (
                        "Uzun süreli hafıza "
                        "geçerli bir JSON "
                        "listesi değil."
                    )
                )

            memories: list[
                MemoryRecord
            ] = []

            for item in data:
                if not isinstance(
                    item,
                    dict,
                ):
                    raise RuntimeError(
                        (
                            "Uzun süreli "
                            "hafızada geçersiz "
                            "kayıt bulundu."
                        )
                    )

                try:
                    memories.append(
                        MemoryRecord
                        .from_dict(item)
                    )

                except ValueError as error:
                    raise RuntimeError(
                        (
                            "Uzun süreli "
                            "hafızada geçersiz "
                            "kayıt bulundu."
                        )
                    ) from error

            return memories

    def save_all(
        self,
        memories: Sequence[
            MemoryRecord
        ],
    ) -> None:
        with self._lock:
            self._path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temp_path = (
                self._path.with_suffix(
                    self._path.suffix
                    + ".tmp"
                )
            )

            try:
                with temp_path.open(
                    "w",
                    encoding="utf-8",
                ) as handle:
                    json.dump(
                        [
                            memory.to_dict()
                            for memory
                            in memories
                        ],
                        handle,
                        ensure_ascii=False,
                        indent=2,
                    )

                    handle.write(
                        "\n"
                    )

                os.replace(
                    temp_path,
                    self._path,
                )

            except OSError as error:
                try:
                    temp_path.unlink(
                        missing_ok=True
                    )
                except OSError:
                    pass

                raise RuntimeError(
                    (
                        "Uzun süreli "
                        "hafıza yazılamadı: "
                        f"{self._path}"
                    )
                ) from error