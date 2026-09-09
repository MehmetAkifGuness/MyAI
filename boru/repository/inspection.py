import json
from collections import Counter
from pathlib import Path

from boru.code_index import RelevantFileRanker, SafeCodeIndex
from boru.repository.models import RepositoryProfile, RepositoryTaskContext
from boru.tools.project_index import SafeProjectFileIndex
from boru.tools.workspace import ReadOnlyWorkspace, WorkspaceAccessError


class RepositoryInspector:
    """Builds a bounded, deterministic map without executing repository content."""

    _LANGUAGES = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".java": "Java",
        ".kt": "Kotlin", ".kts": "Kotlin", ".cs": "C#", ".go": "Go", ".rs": "Rust",
        ".dart": "Dart", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
        ".html": "HTML", ".css": "CSS", ".sql": "SQL", ".sh": "Shell",
    }
    _ENTRY_NAMES = {
        "main.py", "app.py", "manage.py", "main.js", "index.js", "server.js",
        "main.ts", "index.ts", "main.go", "main.rs", "program.cs", "main.dart",
        "dockerfile", "compose.yaml", "compose.yml", "docker-compose.yaml",
        "docker-compose.yml",
    }
    _MANIFEST_NAMES = {
        "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "package.json",
        "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
        "settings.gradle.kts", "pubspec.yaml", "cargo.toml", "go.mod", "gemfile",
        "composer.json",
    }

    def __init__(self, *, max_files: int = 2000, max_file_bytes: int = 128 * 1024):
        self._max_files = max_files
        self._max_file_bytes = max_file_bytes

    def inspect(self, root: Path, *, display_root: str = ".") -> RepositoryProfile:
        index = SafeProjectFileIndex(
            root, max_files=self._max_files, max_depth=12,
            max_file_bytes=self._max_file_bytes,
        )
        paths = index.list_editable_files()
        workspace = ReadOnlyWorkspace(root, max_file_bytes=self._max_file_bytes)
        languages = Counter(
            self._LANGUAGES.get(Path(path).suffix.casefold())
            for path in paths if Path(path).suffix.casefold() in self._LANGUAGES
        )
        manifests = self._manifest_text(paths, workspace)
        frameworks, managers = self._technology(manifests, paths)
        tests = tuple(path for path in paths if self._is_test(path))[:100]
        return RepositoryProfile(
            root=display_root,
            file_count=len(paths),
            languages=tuple(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
            frameworks=tuple(sorted(frameworks)),
            package_managers=tuple(sorted(managers)),
            entry_points=tuple(path for path in paths if Path(path).name.casefold() in self._ENTRY_NAMES)[:30],
            test_files=tests,
            test_commands=self._test_commands(paths, manifests, tests),
            documentation=tuple(path for path in paths if Path(path).suffix.casefold() == ".md")[:30],
            ci_files=tuple(path for path in paths if path.casefold().startswith(".github/workflows/"))[:30],
            license_files=tuple(path for path in paths if Path(path).name.casefold() in {"license", "notice"})[:10],
        )

    def task_context(self, root: Path, objective: str) -> RepositoryTaskContext:
        if not objective.strip() or len(objective) > 4000:
            raise ValueError("Repo görevi 1-4000 karakter arasında olmalıdır.")
        paths = SafeProjectFileIndex(root, max_files=self._max_files, max_depth=12).list_editable_files()
        ranked = RelevantFileRanker(
            SafeCodeIndex(root, max_files=self._max_files), max_candidates=12
        ).rank(objective, paths)
        selected = tuple(ranked[:12])
        reasons = tuple(
            (path, self._context_reason(path, index))
            for index, path in enumerate(selected)
        )
        return RepositoryTaskContext(objective.strip(), selected, reasons)

    def _context_reason(self, path: str, index: int) -> str:
        if self._is_test(path):
            return "ilişkili test adayı"
        if index == 0:
            return "birincil kod eşleşmesi"
        return "yakın ad, yol veya sembol eşleşmesi"

    def _manifest_text(self, paths, workspace) -> dict[str, str]:
        result = {}
        for path in paths:
            name = Path(path).name.casefold()
            if name not in self._MANIFEST_NAMES and not name.startswith("requirements"):
                continue
            try:
                result[path] = workspace.read_text_file(path)[: self._max_file_bytes]
            except (OSError, UnicodeError, WorkspaceAccessError):
                continue
        return result

    @staticmethod
    def _technology(manifests, paths):
        text = "\n".join(manifests.values()).casefold()
        names = {Path(path).name.casefold() for path in paths}
        frameworks = set()
        for token, label in (
            ("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask"),
            ("pytest", "pytest"), ("react", "React"), ("next", "Next.js"),
            ("vue", "Vue"), ("angular", "Angular"), ("spring", "Spring"),
            ("flutter", "Flutter"), ("aspnet", "ASP.NET"),
        ):
            if token in text:
                frameworks.add(label)
        managers = set()
        for filename, label in (
            ("pyproject.toml", "Python/pyproject"), ("requirements.txt", "pip"),
            ("package.json", "npm"), ("pom.xml", "Maven"),
            ("build.gradle", "Gradle"), ("build.gradle.kts", "Gradle"),
            ("pubspec.yaml", "pub"), ("cargo.toml", "Cargo"), ("go.mod", "Go modules"),
        ):
            if filename in names:
                managers.add(label)
        if any(name.startswith("requirements") and name.endswith(".txt") for name in names):
            managers.add("pip")
        return frameworks, managers

    @staticmethod
    def _is_test(path: str) -> bool:
        folded = path.casefold()
        name = Path(folded).name
        return (
            folded.startswith("tests/") or "/tests/" in folded or name.startswith("test_")
            or "_test." in name or name.endswith("tests.py") or name.endswith("test.java")
        )

    @staticmethod
    def _test_commands(paths, manifests, tests):
        names = {Path(path).name.casefold() for path in paths}
        text = "\n".join(manifests.values()).casefold()
        commands = []
        if any(path.endswith(".py") for path in tests):
            commands.append("python -m pytest" if "pytest" in text else "python -m unittest discover")
        if "package.json" in names:
            try:
                package = next(json.loads(value) for path, value in manifests.items() if Path(path).name.casefold() == "package.json")
                if isinstance(package.get("scripts"), dict) and "test" in package["scripts"]:
                    commands.append("npm test")
            except (StopIteration, json.JSONDecodeError, AttributeError):
                pass
        if "pom.xml" in names:
            commands.append("mvn test")
        if {"build.gradle", "build.gradle.kts"} & names:
            commands.append("gradle test")
        if "pubspec.yaml" in names:
            commands.append("flutter test")
        if "cargo.toml" in names:
            commands.append("cargo test")
        if "go.mod" in names:
            commands.append("go test ./...")
        return tuple(dict.fromkeys(commands))
