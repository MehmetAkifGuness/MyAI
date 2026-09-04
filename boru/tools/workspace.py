import fnmatch
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


class WorkspaceAccessError(RuntimeError):
    """Workspace güvenlik sınırı ihlal edildiğinde yükseltilir."""


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    name: str
    relative_path: str
    is_directory: bool
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class DirectoryListing:
    entries: tuple[WorkspaceEntry, ...]
    truncated: bool = False


class WorkspacePathResolver:
    """Göreli yolları tek bir workspace kökü içinde güvenli biçimde çözer."""

    _BLOCKED_SEGMENTS = frozenset(
        {
            ".git",
            ".ssh",
        }
    )

    _BLOCKED_FILE_PATTERNS = (
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa",
        "id_rsa.*",
        "id_ed25519",
        "id_ed25519.*",
        "credentials.json",
        "secrets.json",
    )

    def __init__(
        self,
        root: str | Path,
    ):
        root_path = Path(root).expanduser()

        if not root_path.exists():
            raise ValueError(
                f"Workspace kökü bulunamadı: {root_path}"
            )

        if not root_path.is_dir():
            raise ValueError(
                f"Workspace kökü klasör olmalıdır: {root_path}"
            )

        self._root = root_path.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def resolve(
        self,
        relative_path: str,
        *,
        must_exist: bool = True,
    ) -> Path:
        cleaned = relative_path.strip()

        if not cleaned or cleaned == ".":
            return self._root

        self._reject_absolute_path(cleaned)

        normalized = cleaned.replace("\\", "/")
        parts = PurePosixPath(normalized).parts

        if any(part in {"..", ""} for part in parts):
            raise WorkspaceAccessError(
                "Workspace dışına çıkan göreli yollara izin verilmez."
            )

        self._reject_blocked_parts(parts)
        self._reject_symlink_components(parts)

        candidate = self._root.joinpath(*parts).resolve(
            strict=False
        )

        if not candidate.is_relative_to(self._root):
            raise WorkspaceAccessError(
                "İstenen yol workspace sınırının dışında."
            )

        if must_exist and not candidate.exists():
            raise WorkspaceAccessError(
                f"İstenen yol bulunamadı: {cleaned}"
            )

        return candidate

    def is_visible_child(
        self,
        child: Path,
    ) -> bool:
        try:
            relative = child.relative_to(self._root)
            self.resolve(relative.as_posix())
        except (
            ValueError,
            WorkspaceAccessError,
        ):
            return False

        return True

    @staticmethod
    def _reject_absolute_path(
        value: str,
    ) -> None:
        windows_path = PureWindowsPath(value)

        if (
            Path(value).is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or bool(windows_path.root)
            or PurePosixPath(value).is_absolute()
        ):
            raise WorkspaceAccessError(
                "Mutlak dosya yollarına izin verilmez."
            )

    def _reject_blocked_parts(
        self,
        parts: tuple[str, ...],
    ) -> None:
        folded_parts = tuple(
            part.casefold()
            for part in parts
        )

        if any(
            part in self._BLOCKED_SEGMENTS
            for part in folded_parts
        ):
            raise WorkspaceAccessError(
                "Korunan workspace yoluna erişim engellendi."
            )

        if not folded_parts:
            return

        filename = folded_parts[-1]

        if any(
            fnmatch.fnmatchcase(
                filename,
                pattern.casefold(),
            )
            for pattern in self._BLOCKED_FILE_PATTERNS
        ):
            raise WorkspaceAccessError(
                "Hassas olabilecek dosyaya erişim engellendi."
            )

    def _reject_symlink_components(
        self,
        parts: tuple[str, ...],
    ) -> None:
        current = self._root

        for part in parts:
            current = current / part

            if current.exists() and current.is_symlink():
                raise WorkspaceAccessError(
                    "Sembolik bağlantılar üzerinden erişim engellendi."
                )


class ReadOnlyWorkspace:
    """Workspace içindeki metin dosyalarını ve klasörleri salt-okunur sunar."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_file_bytes: int = 128 * 1024,
        max_directory_entries: int = 200,
    ):
        if max_file_bytes < 1:
            raise ValueError(
                "max_file_bytes en az 1 olmalıdır."
            )

        if max_directory_entries < 1:
            raise ValueError(
                "max_directory_entries en az 1 olmalıdır."
            )

        self._resolver = WorkspacePathResolver(
            root
        )
        self._max_file_bytes = max_file_bytes
        self._max_directory_entries = (
            max_directory_entries
        )

    @property
    def root(self) -> Path:
        return self._resolver.root

    def list_directory(
        self,
        relative_path: str = ".",
    ) -> DirectoryListing:
        target = self._resolver.resolve(
            relative_path
        )

        if not target.is_dir():
            raise WorkspaceAccessError(
                "İstenen yol bir klasör değil."
            )

        visible_children = [
            child
            for child in target.iterdir()
            if self._resolver.is_visible_child(child)
        ]

        visible_children.sort(
            key=lambda child: (
                not child.is_dir(),
                child.name.casefold(),
            )
        )

        truncated = (
            len(visible_children)
            > self._max_directory_entries
        )

        selected = visible_children[
            : self._max_directory_entries
        ]

        entries = tuple(
            self._to_entry(child)
            for child in selected
        )

        return DirectoryListing(
            entries=entries,
            truncated=truncated,
        )

    def read_text_file(
        self,
        relative_path: str,
    ) -> str:
        target = self._resolver.resolve(
            relative_path
        )

        if not target.is_file():
            raise WorkspaceAccessError(
                "İstenen yol bir dosya değil."
            )

        try:
            with target.open("rb") as handle:
                data = handle.read(
                    self._max_file_bytes + 1
                )
        except OSError as error:
            raise WorkspaceAccessError(
                "Dosya güvenli biçimde okunamadı."
            ) from error

        if len(data) > self._max_file_bytes:
            raise WorkspaceAccessError(
                "Dosya izin verilen okuma boyutunu aşıyor."
            )

        if b"\x00" in data:
            raise WorkspaceAccessError(
                "Binary dosyalar read_file ile okunamaz."
            )

        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise WorkspaceAccessError(
                "Dosya UTF-8 metin olarak okunamadı."
            ) from error

    def _to_entry(
        self,
        child: Path,
    ) -> WorkspaceEntry:
        relative_path = child.relative_to(
            self._resolver.root
        ).as_posix()

        is_directory = child.is_dir()

        size_bytes = None
        if child.is_file():
            try:
                size_bytes = child.stat().st_size
            except OSError:
                size_bytes = None

        return WorkspaceEntry(
            name=child.name,
            relative_path=relative_path,
            is_directory=is_directory,
            size_bytes=size_bytes,
        )