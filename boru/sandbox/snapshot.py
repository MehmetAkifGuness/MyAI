import os
from pathlib import Path

from boru.tools.workspace import ReadOnlyWorkspace, WorkspacePathResolver


class SourceSnapshot:
    """Copies bounded source files, excluding runtime data and linked paths."""

    _EXCLUDED = {"data", "ai_hafiza", "node_modules", "__pycache__", "build", "dist"}
    _SUFFIXES = {".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml", ".csv"}

    def __init__(self, root: Path, max_files: int = 2000, max_bytes: int = 16 * 1024 * 1024):
        self._resolver = WorkspacePathResolver(root)
        self._reader = ReadOnlyWorkspace(root, max_file_bytes=1024 * 1024)
        self._max_files = max_files
        self._max_bytes = max_bytes

    def copy_to(self, destination: Path) -> dict[str, bytes]:
        # destination is an empty, caller-owned temporary directory.
        if any(destination.iterdir()):
            raise ValueError("Sandbox hedef klasörü boş olmalıdır.")
        destination.chmod(0o755)
        contents = self.read_sources()
        for relative, content in contents.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return contents

    def read_sources(self) -> dict[str, bytes]:
        contents: dict[str, bytes] = {}
        total = 0
        for directory, dirs, files in os.walk(self._resolver.root, followlinks=False):
            parent = Path(directory)
            dirs[:] = sorted(
                name for name in dirs
                if not name.startswith(".") and name.casefold() not in self._EXCLUDED
                and self._visible(parent / name)
            )
            for name in sorted(files):
                path = parent / name
                if name.startswith(".") or path.suffix.casefold() not in self._SUFFIXES:
                    continue
                if not self._visible(path):
                    continue
                relative = path.relative_to(self._resolver.root).as_posix()
                content = self._reader.read_text_file(relative).encode("utf-8")
                total += len(content)
                if len(contents) >= self._max_files or total > self._max_bytes:
                    raise ValueError("Sandbox kaynak kopyası boyut/dosya sınırını aştı.")
                contents[relative] = content
        return contents

    def _visible(self, path: Path) -> bool:
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            return False
        return self._resolver.is_visible_child(path)
