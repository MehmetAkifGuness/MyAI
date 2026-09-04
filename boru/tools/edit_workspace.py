import difflib
import hashlib
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from boru.tools.edit_models import (
    EditOutcome,
    EditProposal,
    EditRequest,
)


class WorkspaceEditError(ValueError):
    pass


class SafeEditWorkspace:
    """Workspace içindeki mevcut UTF-8 metin dosyalarını kontrollü ve atomik düzenler."""

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
                "Edit workspace kökü mevcut değil."
            )

        if not root_path.is_dir():
            raise ValueError(
                "Edit workspace kökü klasör olmalıdır."
            )

        if max_bytes < 1:
            raise ValueError(
                "max_bytes en az 1 olmalıdır."
            )

        self._root = root_path.resolve()
        self._max_bytes = max_bytes

    @property
    def root(self) -> Path:
        return self._root

    def prepare_exact_replacement(
        self,
        request: EditRequest,
    ) -> EditProposal:
        target = self._resolve_existing_file(
            request.path
        )

        raw, original, had_bom = self._read_utf8(
            target
        )

        occurrences = original.count(
            request.old_text
        )

        if occurrences == 0:
            raise WorkspaceEditError(
                "Değiştirilecek eski içerik hedef dosyada bulunamadı."
            )

        if occurrences > 1:
            raise WorkspaceEditError(
                "Değiştirilecek eski içerik dosyada birden fazla kez bulundu; işlem belirsiz olduğu için reddedildi."
            )

        updated = original.replace(
            request.old_text,
            request.new_text,
            1,
        )

        encoded = self._encode_text(
            updated,
            had_bom=had_bom,
        )

        if len(encoded) > self._max_bytes:
            raise WorkspaceEditError(
                "Düzenlenmiş dosya izin verilen yazma sınırını aşıyor."
            )

        display_path = self._display_path(
            target
        )

        diff = "".join(
            difflib.unified_diff(
                original.splitlines(
                    keepends=True
                ),
                updated.splitlines(
                    keepends=True
                ),
                fromfile=(
                    f"{display_path} (mevcut)"
                ),
                tofile=(
                    f"{display_path} (önerilen)"
                ),
                lineterm="\n",
            )
        )

        return EditProposal(
            path=display_path,
            updated_content=updated,
            expected_sha256=(
                hashlib.sha256(raw).hexdigest()
            ),
            diff=diff,
            original_character_count=len(
                original
            ),
            updated_character_count=len(
                updated
            ),
        )

    def apply_text_update(
        self,
        *,
        relative_path: str,
        content: str,
        expected_sha256: str,
    ) -> EditOutcome:
        target = self._resolve_existing_file(
            relative_path
        )

        current_raw, _, had_bom = self._read_utf8(
            target
        )

        current_hash = hashlib.sha256(
            current_raw
        ).hexdigest()

        if current_hash != expected_sha256:
            raise WorkspaceEditError(
                "Dosya önizlemeden sonra değişmiş. Güvenlik nedeniyle düzenleme uygulanmadı; isteği yeniden hazırla."
            )

        if "\x00" in content:
            raise WorkspaceEditError(
                "NUL karakteri içeren metin yazılamaz."
            )

        encoded = self._encode_text(
            content,
            had_bom=had_bom,
        )

        if len(encoded) > self._max_bytes:
            raise WorkspaceEditError(
                "Dosya içeriği izin verilen yazma sınırını aşıyor."
            )

        self._reject_symlink_components(
            target
        )

        self._atomic_replace(
            target,
            encoded,
        )

        return EditOutcome(
            relative_path=self._display_path(
                target
            ),
            character_count=len(content),
            byte_count=len(encoded),
        )

    def _resolve_existing_file(
        self,
        relative_path: str,
    ) -> Path:
        target = self._resolve_target(
            relative_path
        )

        self._reject_symlink_components(
            target
        )

        if not target.exists():
            raise WorkspaceEditError(
                "Düzenlenecek hedef dosya mevcut değil."
            )

        if not target.is_file():
            raise WorkspaceEditError(
                "Düzenleme hedefi normal bir dosya değil."
            )

        return target

    def _resolve_target(
        self,
        relative_path: str,
    ) -> Path:
        cleaned = relative_path.strip()

        if not cleaned:
            raise WorkspaceEditError(
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
            raise WorkspaceEditError(
                "Mutlak dosya yollarını düzenleme izni yok."
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
            raise WorkspaceEditError(
                "Hedef dosya yolu geçersiz."
            )

        if ".." in parts:
            raise WorkspaceEditError(
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
            raise WorkspaceEditError(
                "Hedef yol workspace dışında."
            ) from error

        return target

    def _reject_sensitive_parts(
        self,
        parts: tuple[str, ...],
    ) -> None:
        for part in parts:
            if part.casefold() in self._BLOCKED_SEGMENTS:
                raise WorkspaceEditError(
                    "Hassas klasörde dosya düzenleme erişimi engellendi."
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
            raise WorkspaceEditError(
                "Hassas olabilecek dosyayı düzenleme erişimi engellendi."
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
                raise WorkspaceEditError(
                    "Sembolik bağlantı üzerinden dosya düzenleme engellendi."
                )

    def _read_utf8(
        self,
        target: Path,
    ) -> tuple[bytes, str, bool]:
        raw = target.read_bytes()

        if len(raw) > self._max_bytes:
            raise WorkspaceEditError(
                "Dosya izin verilen düzenleme sınırını aşıyor."
            )

        if b"\x00" in raw:
            raise WorkspaceEditError(
                "Binary/NUL içeren dosya düzenlenemez."
            )

        had_bom = raw.startswith(
            b"\xef\xbb\xbf"
        )

        try:
            text = raw.decode(
                "utf-8-sig"
            )
        except UnicodeDecodeError as error:
            raise WorkspaceEditError(
                "Yalnızca UTF-8 metin dosyaları düzenlenebilir."
            ) from error

        return raw, text, had_bom

    @staticmethod
    def _encode_text(
        content: str,
        *,
        had_bom: bool,
    ) -> bytes:
        encoded = content.encode(
            "utf-8"
        )

        if had_bom:
            return (
                b"\xef\xbb\xbf"
                + encoded
            )

        return encoded

    @staticmethod
    def _atomic_replace(
        target: Path,
        encoded: bytes,
    ) -> None:
        original_mode = stat.S_IMODE(
            target.stat().st_mode
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(
                    handle.name
                )

                handle.write(
                    encoded
                )

                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            try:
                os.chmod(
                    temporary_path,
                    original_mode,
                )
            except OSError:
                pass

            os.replace(
                temporary_path,
                target,
            )

            temporary_path = None

        finally:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

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