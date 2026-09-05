from pathlib import Path
from threading import RLock

from boru.persistence import AtomicJsonFileStore, JsonFileReadError, JsonFileWriteError


class JsonProjectMemoryRepository:
    """Proje bilgilerini atomik bir JSON belgesinde saklar."""

    _VERSION = 1

    def __init__(self, file_path: str | Path):
        self._store = AtomicJsonFileStore(file_path)
        self._lock = RLock()

    def load(self) -> dict[str, str]:
        with self._lock:
            try:
                data = self._store.read()
            except JsonFileReadError as error:
                raise RuntimeError(
                    f"Proje hafızası okunamadı: {self._store.path}"
                ) from error

            if data is None:
                return {}

            if not isinstance(data, dict) or data.get("version") != self._VERSION:
                raise RuntimeError("Proje hafızası geçerli bir V1 JSON nesnesi değil.")

            entries = data.get("entries")
            if not isinstance(entries, dict):
                raise RuntimeError("Proje hafızası geçerli bir kayıt haritası içermiyor.")

            if not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in entries.items()
            ):
                raise RuntimeError("Proje hafızasında geçersiz kayıt bulundu.")

            return dict(entries)

    def save(self, entries: dict[str, str]) -> None:
        with self._lock:
            try:
                self._store.write(
                    {
                        "version": self._VERSION,
                        "entries": dict(sorted(entries.items())),
                    }
                )
            except JsonFileWriteError as error:
                raise RuntimeError(
                    f"Proje hafızası yazılamadı: {self._store.path}"
                ) from error
