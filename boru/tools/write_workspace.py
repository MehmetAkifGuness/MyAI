import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from boru.tools.write_models import (
    WriteOutcome,
)


class WorkspaceWriteError(
    ValueError
):
    pass


class SafeWriteWorkspace:
    """Workspace içinde yalnızca yeni UTF-8 metin dosyası oluşturur."""

    _BLOCKED_SEGMENTS = {
        ".git",
        ".ssh",
    }

    _BLOCKED_FILENAMES = {
        ".env",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    }

    _BLOCKED_SUFFIXES = (
        ".pem",
        ".key",
    )

    def __init__(
        self,
        root: str | Path,
        *,
        max_bytes: int = 128 * 1024,
    ):
        root_path = Path(root)

        if not root_path.exists():
            raise ValueError(
                "Write workspace kökü mevcut değil."
            )

        if not root_path.is_dir():
            raise ValueError(
                "Write workspace kökü klasör olmalıdır."
            )

        if max_bytes < 1:
            raise ValueError(
                "max_bytes en az 1 olmalıdır."
            )

        self._root = root_path.resolve()
        self._max_bytes = max_bytes

    @property
    def root(
        self,
    ) -> Path:
        return self._root

    def write_text_file(
        self,
        relative_path: str,
        content: str,
    ) -> WriteOutcome:
        target, encoded = self._validate_new_text_file(
            relative_path,
            content,
        )

        descriptor: int | None = None

        try:
            descriptor = os.open(
                target,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL,
                0o600,
            )

            with os.fdopen(
                descriptor,
                "wb",
            ) as handle:
                descriptor = None

                handle.write(
                    encoded
                )

                handle.flush()

                os.fsync(
                    handle.fileno()
                )

        except FileExistsError as error:
            raise WorkspaceWriteError(
                "Hedef dosya zaten mevcut. "
                "Bu sürüm mevcut dosyanın üzerine yazmaz."
            ) from error

        except Exception:
            if descriptor is not None:
                os.close(
                    descriptor
                )

            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass

            raise

        return WriteOutcome(
            relative_path=self._display_path(
                target
            ),
            character_count=len(content),
            byte_count=len(encoded),
        )

    def validate_new_text_file(
        self,
        relative_path: str,
        content: str,
    ) -> None:
        self._validate_new_text_file(
            relative_path,
            content,
        )

    def remove_created_text_file(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
    ) -> None:
        target = self._resolve_target(
            relative_path
        )
        self._reject_symlink_components(
            target
        )

        if not target.is_file():
            raise WorkspaceWriteError(
                "Rollback hedefi normal bir dosya değil."
            )

        current_hash = hashlib.sha256(
            target.read_bytes()
        ).hexdigest()

        if current_hash != expected_sha256:
            raise WorkspaceWriteError(
                "Rollback hedefi transaction sonrasında dışarıdan değişmiş; "
                "harici değişiklik korunmak için dosya silinmedi."
            )

        target.unlink()

    def _validate_new_text_file(
        self,
        relative_path: str,
        content: str,
    ) -> tuple[Path, bytes]:
        target = self._resolve_target(
            relative_path
        )

        if "\x00" in content:
            raise WorkspaceWriteError(
                "NUL karakteri içeren metin yazılamaz."
            )

        encoded = content.encode(
            "utf-8"
        )

        if len(encoded) > self._max_bytes:
            raise WorkspaceWriteError(
                "Dosya içeriği izin verilen yazma sınırını aşıyor."
            )

        if target.exists():
            raise WorkspaceWriteError(
                "Hedef dosya zaten mevcut. "
                "Bu sürüm mevcut dosyanın üzerine yazmaz."
            )

        parent = target.parent

        if not parent.exists():
            raise WorkspaceWriteError(
                "Hedef klasör mevcut değil."
            )

        if not parent.is_dir():
            raise WorkspaceWriteError(
                "Hedef üst yol bir klasör değil."
            )

        self._reject_symlink_components(
            target
        )

        return target, encoded

    def _resolve_target(
        self,
        relative_path: str,
    ) -> Path:
        cleaned = relative_path.strip()

        if not cleaned:
            raise WorkspaceWriteError(
                "Hedef dosya yolu boş olamaz."
            )

        windows_path = PureWindowsPath(
            cleaned
        )

        posix_path = PurePosixPath(
            cleaned.replace(
                "\\",
                "/",
            )
        )

        if (
            windows_path.is_absolute()
            or windows_path.drive
            or posix_path.is_absolute()
        ):
            raise WorkspaceWriteError(
                "Mutlak dosya yollarına yazma izni yok."
            )

        parts = tuple(
            part
            for part in posix_path.parts
            if part not in {
                "",
                ".",
            }
        )

        if not parts:
            raise WorkspaceWriteError(
                "Hedef dosya yolu geçersiz."
            )

        if ".." in parts:
            raise WorkspaceWriteError(
                "Workspace dışına çıkan yol kullanılamaz."
            )

        self._reject_sensitive_parts(
            parts
        )

        target = self._root.joinpath(
            *parts
        )

        try:
            target.relative_to(
                self._root
            )
        except ValueError as error:
            raise WorkspaceWriteError(
                "Hedef yol workspace dışında."
            ) from error

        return target

    def _reject_sensitive_parts(
        self,
        parts: tuple[str, ...],
    ) -> None:
        for part in parts:
            folded = part.casefold()

            if folded in self._BLOCKED_SEGMENTS:
                raise WorkspaceWriteError(
                    "Hassas klasöre yazma erişimi engellendi."
                )

        filename = parts[-1].casefold()

        if (
            filename in self._BLOCKED_FILENAMES
            or filename.startswith(
                ".env."
            )
            or filename.endswith(
                self._BLOCKED_SUFFIXES
            )
        ):
            raise WorkspaceWriteError(
                "Hassas olabilecek dosyaya yazma erişimi engellendi."
            )

    def _reject_symlink_components(
        self,
        target: Path,
    ) -> None:
        relative = target.relative_to(
            self._root
        )

        current = self._root

        for part in relative.parts:
            current = current / part

            if (
                current.exists()
                and current.is_symlink()
            ):
                raise WorkspaceWriteError(
                    "Sembolik bağlantı üzerinden yazma engellendi."
                )

    def _display_path(
        self,
        target: Path,
    ) -> str:
        return (
            target.relative_to(
                self._root
            )
            .as_posix()
        )
