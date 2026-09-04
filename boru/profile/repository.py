from pathlib import Path
from threading import RLock

from boru.persistence import (
    AtomicJsonFileStore,
    JsonFileReadError,
    JsonFileWriteError,
)
from boru.profile.models import UserProfile


class JsonUserProfileRepository:
    """Kullanıcı profilini dayanıklı JSON depolamada saklar."""

    def __init__(
        self,
        file_path: str | Path,
    ):
        self._store = AtomicJsonFileStore(
            file_path
        )
        self._lock = RLock()

    def load(self) -> UserProfile:
        with self._lock:
            try:
                data = self._store.read()
            except JsonFileReadError as error:
                raise RuntimeError(
                    f"Kullanıcı profili okunamadı: {self._store.path}"
                ) from error

            if data is None:
                return UserProfile()

            if not isinstance(data, dict):
                raise RuntimeError(
                    "Kullanıcı profili geçerli bir JSON nesnesi değil."
                )

            return UserProfile.from_dict(
                data
            )

    def save(
        self,
        profile: UserProfile,
    ) -> None:
        with self._lock:
            try:
                self._store.write(
                    profile.to_dict()
                )
            except JsonFileWriteError as error:
                raise RuntimeError(
                    f"Kullanıcı profili yazılamadı: {self._store.path}"
                ) from error