import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from boru.tools.filesystem_models import (
    FilesystemOperation,
    FilesystemOperationOutcome,
    FilesystemOperationProposal,
    FilesystemOperationRequest,
)


class FilesystemOperationError(ValueError):
    pass


class SafeFilesystemOperationWorkspace:
    """Workspace içinde sınırlı ve stale-korumalı dosya sistemi işlemleri uygular."""

    _BLOCKED_SEGMENTS = {".git", ".ssh"}
    _BLOCKED_FILENAMES = {
        ".env",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    }
    _BLOCKED_SUFFIXES = (".pem", ".key")

    def __init__(
        self,
        root: str | Path,
        *,
        max_source_bytes: int = 128 * 1024,
    ):
        root_path = Path(root)
        if not root_path.is_dir():
            raise ValueError("Filesystem workspace kökü mevcut bir klasör olmalıdır.")
        if max_source_bytes < 1:
            raise ValueError("max_source_bytes en az 1 olmalıdır.")

        self._root = root_path.resolve()
        self._max_source_bytes = max_source_bytes

    def prepare(
        self,
        request: FilesystemOperationRequest,
    ) -> FilesystemOperationProposal:
        if request.operation is FilesystemOperation.MAKE_DIRECTORY:
            self._new_target(request.source_path)
            return FilesystemOperationProposal(request=request)

        source = self._existing_file(request.source_path)
        raw = source.read_bytes()
        if len(raw) > self._max_source_bytes:
            raise FilesystemOperationError(
                "Kaynak dosya izin verilen işlem boyutu sınırını aşıyor."
            )

        if request.destination_path is not None:
            self._new_target(request.destination_path)

        return FilesystemOperationProposal(
            request=request,
            expected_source_sha256=hashlib.sha256(raw).hexdigest(),
            source_byte_count=len(raw),
        )

    def apply(
        self,
        proposal: FilesystemOperationProposal,
    ) -> FilesystemOperationOutcome:
        current = self.prepare(
            proposal.request
        )
        if current.expected_source_sha256 != proposal.expected_source_sha256:
            raise FilesystemOperationError(
                "Kaynak dosya önizlemeden sonra değişmiş; işlem uygulanmadı."
            )

        request = proposal.request
        source = self._resolve_target(
            request.source_path
        )

        if request.operation is FilesystemOperation.DELETE_FILE:
            source.unlink()
        elif request.operation is FilesystemOperation.MAKE_DIRECTORY:
            os.mkdir(source)
        else:
            destination = self._resolve_target(
                request.destination_path or ""
            )
            self._move_without_overwrite(
                source,
                destination,
                expected_sha256=proposal.expected_source_sha256 or "",
            )

        return FilesystemOperationOutcome(
            operation=request.operation,
            source_path=request.source_path,
            destination_path=request.destination_path,
        )

    def _move_without_overwrite(
        self,
        source: Path,
        destination: Path,
        *,
        expected_sha256: str,
    ) -> None:
        try:
            os.link(
                source,
                destination,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            raise FilesystemOperationError(
                "Hedef yol önizlemeden sonra oluşturulmuş; işlem uygulanmadı."
            ) from error
        except OSError as error:
            raise FilesystemOperationError(
                f"Dosya güvenli biçimde taşınamadı: {error}"
            ) from error

        try:
            source.unlink()
        except Exception as error:
            try:
                if self._hash_file(destination) == expected_sha256:
                    destination.unlink()
            except OSError:
                raise RuntimeError(
                    "Taşıma tamamlanamadı ve oluşturulan hedef geri alınamadı."
                ) from error

            raise FilesystemOperationError(
                "Taşıma tamamlanamadı; oluşturulan hedef geri alındı."
            ) from error

    def _existing_file(
        self,
        relative_path: str,
    ) -> Path:
        target = self._resolve_target(relative_path)
        self._reject_symlink_components(target)
        if not target.exists():
            raise FilesystemOperationError("Kaynak dosya mevcut değil.")
        if not target.is_file():
            raise FilesystemOperationError("Kaynak normal bir dosya olmalıdır.")
        return target

    def _new_target(
        self,
        relative_path: str,
    ) -> Path:
        target = self._resolve_target(relative_path)
        self._reject_symlink_components(target)
        if target.exists():
            raise FilesystemOperationError("Hedef yol zaten mevcut.")
        if not target.parent.is_dir():
            raise FilesystemOperationError("Hedef üst klasör mevcut değil.")
        return target

    def _resolve_target(
        self,
        relative_path: str,
    ) -> Path:
        cleaned = relative_path.strip().strip("\"'")
        windows_path = PureWindowsPath(cleaned)
        posix_path = PurePosixPath(cleaned.replace("\\", "/"))

        if not cleaned or windows_path.is_absolute() or windows_path.drive or posix_path.is_absolute():
            raise FilesystemOperationError("Yalnızca göreli workspace yolları kullanılabilir.")

        parts = tuple(part for part in posix_path.parts if part not in {"", "."})
        if not parts or ".." in parts:
            raise FilesystemOperationError("Workspace dışına çıkan yol kullanılamaz.")

        self._reject_sensitive_parts(parts)
        target = self._root.joinpath(*parts)
        try:
            target.relative_to(self._root)
        except ValueError as error:
            raise FilesystemOperationError("Hedef yol workspace dışında.") from error
        return target

    def _reject_sensitive_parts(
        self,
        parts: tuple[str, ...],
    ) -> None:
        if any(part.casefold() in self._BLOCKED_SEGMENTS for part in parts):
            raise FilesystemOperationError("Hassas klasörde işlem engellendi.")

        filename = parts[-1].casefold()
        if (
            filename in self._BLOCKED_FILENAMES
            or filename.startswith(".env.")
            or filename.endswith(self._BLOCKED_SUFFIXES)
        ):
            raise FilesystemOperationError("Hassas dosyada işlem engellendi.")

    def _reject_symlink_components(
        self,
        target: Path,
    ) -> None:
        current = self._root
        for part in target.relative_to(self._root).parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise FilesystemOperationError(
                    "Sembolik bağlantı üzerinden dosya sistemi işlemi engellendi."
                )

    @staticmethod
    def _hash_file(
        path: Path,
    ) -> str:
        return hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
