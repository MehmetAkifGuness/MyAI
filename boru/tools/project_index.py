from pathlib import Path

from boru.tools.workspace import (
    WorkspaceAccessError,
    WorkspacePathResolver,
)


class SafeProjectFileIndex:
    """LLM'e yalnızca güvenli ve sınırlı project file manifest'i sunar."""

    _EXCLUDED_DIRECTORIES = {
        ".git",
        ".ssh",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        "env",
        "data",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "build",
        "dist",
        "coverage",
        "htmlcov",
    }

    _ALLOWED_SUFFIXES = {
        ".py",
        ".toml",
        ".json",
        ".yaml",
        ".yml",
        ".md",
        ".txt",
        ".ini",
        ".cfg",
        ".csv",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".dart",
        ".java",
        ".cs",
        ".sql",
        ".go",
        ".rs",
        ".kt",
        ".kts",
        ".rb",
        ".php",
        ".swift",
        ".sh",
        ".lock",
    }

    _ALLOWED_NAMES = {
        "dockerfile",
        "makefile",
        "license",
        "notice",
    }

    def __init__(
        self,
        root: str | Path,
        *,
        max_files: int = 200,
        max_depth: int = 8,
        max_file_bytes: int = 128 * 1024,
    ):
        if max_files < 1:
            raise ValueError(
                "max_files en az 1 olmalıdır."
            )

        if max_depth < 1:
            raise ValueError(
                "max_depth en az 1 olmalıdır."
            )

        if max_file_bytes < 1:
            raise ValueError(
                "max_file_bytes en az 1 olmalıdır."
            )

        self._resolver = WorkspacePathResolver(
            root
        )
        self._max_files = max_files
        self._max_depth = max_depth
        self._max_file_bytes = max_file_bytes

    @property
    def root(self) -> Path:
        return self._resolver.root

    def list_editable_files(
        self,
    ) -> tuple[str, ...]:
        results: list[str] = []

        self._walk(
            directory=self._resolver.root,
            depth=0,
            results=results,
        )

        results.sort(
            key=str.casefold
        )

        return tuple(
            results[: self._max_files]
        )

    def _walk(
        self,
        *,
        directory: Path,
        depth: int,
        results: list[str],
    ) -> None:
        if (
            depth > self._max_depth
            or len(results) >= self._max_files
        ):
            return

        try:
            children = sorted(
                directory.iterdir(),
                key=lambda item: item.name.casefold(),
            )
        except OSError:
            return

        for child in children:
            if len(results) >= self._max_files:
                return

            name_folded = child.name.casefold()

            if child.is_symlink():
                continue

            if child.is_dir():
                if (
                    (name_folded.startswith(".") and name_folded != ".github")
                    or name_folded
                    in self._EXCLUDED_DIRECTORIES
                ):
                    continue

                self._walk(
                    directory=child,
                    depth=depth + 1,
                    results=results,
                )
                continue

            if not child.is_file():
                continue

            if (
                child.suffix.casefold() not in self._ALLOWED_SUFFIXES
                and name_folded not in self._ALLOWED_NAMES
            ):
                continue

            try:
                if child.stat().st_size > self._max_file_bytes:
                    continue

                relative = child.relative_to(
                    self._resolver.root
                ).as_posix()

                self._resolver.resolve(
                    relative
                )
            except (
                OSError,
                ValueError,
                WorkspaceAccessError,
            ):
                continue

            results.append(
                relative
            )
