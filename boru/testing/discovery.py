import ast
import re
from pathlib import Path

from boru.testing.models import RelatedTestSelection
from boru.tools.workspace import WorkspaceAccessError, WorkspacePathResolver


class RelatedTestDiscovery:
    """Kaynak adları ve sembollerinden ilişkili mevcut unittest dosyalarını bulur."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_test_files: int = 8,
        max_file_bytes: int = 128 * 1024,
    ) -> None:
        if max_test_files < 1 or max_file_bytes < 1:
            raise ValueError("Test keşif sınırları pozitif olmalıdır.")
        self._resolver = WorkspacePathResolver(workspace_root)
        self._max_test_files = max_test_files
        self._max_file_bytes = max_file_bytes

    def discover(self, source_paths: tuple[str, ...]) -> RelatedTestSelection:
        normalized_sources: list[str] = []
        source_evidence: list[tuple[str, frozenset[str]]] = []
        for relative_path in source_paths:
            target = self._resolver.resolve(relative_path)
            if not target.is_file():
                raise WorkspaceAccessError(f"Kaynak yolu dosya değil: {relative_path}")
            normalized = target.relative_to(self._resolver.root).as_posix()
            normalized_sources.append(normalized)
            source_evidence.append((normalized, self._symbols(target)))

        scored: list[tuple[int, str]] = []
        for candidate in self._test_candidates():
            relative = candidate.relative_to(self._resolver.root).as_posix()
            score = self._score(relative, candidate, source_evidence)
            if score > 0:
                scored.append((score, relative))

        scored.sort(key=lambda item: (-item[0], item[1].casefold()))
        return RelatedTestSelection(
            source_paths=tuple(normalized_sources),
            test_paths=tuple(path for _, path in scored[: self._max_test_files]),
        )

    def _test_candidates(self) -> tuple[Path, ...]:
        candidates: list[Path] = []
        tests_directory = self._resolver.root / "tests"
        if tests_directory.is_dir() and not tests_directory.is_symlink():
            for candidate in tests_directory.rglob("test_*.py"):
                if candidate.is_file() and self._resolver.is_visible_child(candidate):
                    candidates.append(candidate)
        for candidate in self._resolver.root.glob("*_test.py"):
            if candidate.is_file() and self._resolver.is_visible_child(candidate):
                candidates.append(candidate)
        return tuple(sorted(set(candidates), key=lambda path: path.as_posix().casefold()))

    def _score(
        self,
        test_path: str,
        candidate: Path,
        sources: list[tuple[str, frozenset[str]]],
    ) -> int:
        folded_test_path = test_path.casefold()
        try:
            content = self._read(candidate)
        except (OSError, UnicodeDecodeError, WorkspaceAccessError):
            return 0
        if not self._contains_tests(content):
            return 0

        score = 0
        for source_path, symbols in sources:
            folded_source = source_path.casefold()
            if folded_test_path == folded_source:
                score += 100
                continue

            source_stem = Path(source_path).stem.casefold()
            module_name = source_path.removesuffix(".py").replace("/", ".")
            if source_stem and source_stem in Path(test_path).stem.casefold():
                score += 12
            if module_name in content:
                score += 10
            if source_path in content:
                score += 10
            score += min(
                sum(
                    1
                    for symbol in symbols
                    if re.search(rf"\b{re.escape(symbol)}\b", content)
                ),
                8,
            ) * 3
        return score

    @staticmethod
    def _contains_tests(content: str) -> bool:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False
        return any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (node.name.startswith("test_") or node.name == "load_tests")
            for node in ast.walk(tree)
        )

    def _symbols(self, path: Path) -> frozenset[str]:
        try:
            tree = ast.parse(self._read(path))
        except (OSError, UnicodeDecodeError, SyntaxError, WorkspaceAccessError):
            return frozenset()
        return frozenset(
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
            and len(node.name) >= 4
        )

    def _read(self, path: Path) -> str:
        if path.stat().st_size > self._max_file_bytes:
            raise WorkspaceAccessError("Dosya test keşif okuma sınırını aşıyor.")
        return path.read_text(encoding="utf-8-sig")
