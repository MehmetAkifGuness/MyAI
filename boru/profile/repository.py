import json
import os
from pathlib import Path
from threading import RLock

from boru.profile.models import (
    UserProfile,
)


class JsonUserProfileRepository:
    """
    UserProfile verisini JSON dosyasında
    güvenli biçimde saklar.
    """

    def __init__(
        self,
        file_path: str | Path,
    ):
        self._path = Path(
            file_path
        )

        self._lock = RLock()

    def load(
        self,
    ) -> UserProfile:
        with self._lock:
            if not self._path.exists():
                return UserProfile()

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
                        "Kullanıcı profili "
                        "okunamadı: "
                        f"{self._path}"
                    )
                ) from error

            if not isinstance(
                data,
                dict,
            ):
                raise RuntimeError(
                    (
                        "Kullanıcı profili "
                        "geçerli bir JSON "
                        "nesnesi değil."
                    )
                )

            return (
                UserProfile.from_dict(
                    data
                )
            )

    def save(
        self,
        profile: UserProfile,
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
                        profile.to_dict(),
                        handle,
                        ensure_ascii=False,
                        indent=2,
                    )

                    handle.write("\n")

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
                        "Kullanıcı profili "
                        "yazılamadı: "
                        f"{self._path}"
                    )
                ) from error