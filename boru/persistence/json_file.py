import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class JsonFileReadError(RuntimeError):
    """JSON dosyası güvenilir biçimde okunamadığında yükseltilir."""


class JsonFileWriteError(RuntimeError):
    """JSON dosyası atomik olarak yazılamadığında yükseltilir."""


class AtomicJsonFileStore:
    """
    JSON dosya I/O ayrıntılarını tek yerde toplar.

    Okuma UTF-8 ve UTF-8 BOM dosyalarını kabul eder.
    Yazma her zaman BOM'suz UTF-8 üretir ve aynı dizindeki
    benzersiz geçici dosya üzerinden atomik ``os.replace`` kullanır.
    """

    def __init__(
        self,
        file_path: str | Path,
    ):
        self._path = Path(file_path)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> Any | None:
        if not self._path.exists():
            return None

        try:
            with self._path.open(
                "r",
                encoding="utf-8-sig",
            ) as handle:
                return json.load(handle)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            raise JsonFileReadError(
                f"JSON dosyası okunamadı: {self._path}"
            ) from error

    def write(
        self,
        data: Any,
    ) -> None:
        temp_path: Path | None = None

        try:
            self._path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)

                json.dump(
                    data,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )

                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temp_path,
                self._path,
            )
        except (
            OSError,
            TypeError,
            ValueError,
        ) as error:
            self._cleanup_temp_file(
                temp_path
            )

            raise JsonFileWriteError(
                f"JSON dosyası yazılamadı: {self._path}"
            ) from error

    @staticmethod
    def _cleanup_temp_file(
        temp_path: Path | None,
    ) -> None:
        if temp_path is None:
            return

        try:
            temp_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass