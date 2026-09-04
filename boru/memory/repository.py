from collections.abc import Sequence
from pathlib import Path
from threading import RLock

from boru.memory.models import MemoryRecord
from boru.persistence import (
    AtomicJsonFileStore,
    JsonFileReadError,
    JsonFileWriteError,
)


class JsonMemoryRepository:
    """Uzun süreli hafıza kayıtlarını dayanıklı JSON depolamada saklar."""

    def __init__(
        self,
        file_path: str | Path,
    ):
        self._store = AtomicJsonFileStore(
            file_path
        )
        self._lock = RLock()

    def load_all(self) -> list[MemoryRecord]:
        with self._lock:
            try:
                data = self._store.read()
            except JsonFileReadError as error:
                raise RuntimeError(
                    f"Uzun süreli hafıza okunamadı: {self._store.path}"
                ) from error

            if data is None:
                return []

            if not isinstance(data, list):
                raise RuntimeError(
                    "Uzun süreli hafıza geçerli bir JSON listesi değil."
                )

            memories: list[MemoryRecord] = []

            for item in data:
                if not isinstance(item, dict):
                    raise RuntimeError(
                        "Uzun süreli hafızada geçersiz kayıt bulundu."
                    )

                try:
                    memories.append(
                        MemoryRecord.from_dict(
                            item
                        )
                    )
                except ValueError as error:
                    raise RuntimeError(
                        "Uzun süreli hafızada geçersiz kayıt bulundu."
                    ) from error

            return memories

    def save_all(
        self,
        memories: Sequence[MemoryRecord],
    ) -> None:
        with self._lock:
            try:
                self._store.write(
                    [
                        memory.to_dict()
                        for memory in memories
                    ]
                )
            except JsonFileWriteError as error:
                raise RuntimeError(
                    f"Uzun süreli hafıza yazılamadı: {self._store.path}"
                ) from error