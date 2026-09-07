import ast
from collections import defaultdict, deque
from pathlib import Path

from boru.code_index.models import ImpactedCodeFile
from boru.tools.project_index import SafeProjectFileIndex
from boru.tools.workspace import ReadOnlyWorkspace, WorkspaceAccessError


class SafeCodeImpactIndex:
    """Find bounded direct and transitive reverse-import dependants."""

    def __init__(self, root: str | Path, *, max_files: int = 1000) -> None:
        self._files = SafeProjectFileIndex(root, max_files=max_files)
        self._workspace = ReadOnlyWorkspace(root)

    def impacted_files(
        self,
        source_path: str,
        *,
        max_depth: int = 3,
        max_results: int = 20,
    ) -> tuple[ImpactedCodeFile, ...]:
        if max_depth < 1 or max_depth > 5:
            raise ValueError("Etki analizi derinliği 1 ile 5 arasında olmalıdır.")
        if max_results < 1 or max_results > 50:
            raise ValueError("Etki analizi sonuç sınırı 1 ile 50 arasında olmalıdır.")
        normalized = source_path.strip().replace("\\", "/")
        paths = tuple(
            path for path in self._files.list_editable_files() if path.endswith(".py")
        )
        if normalized not in paths:
            raise WorkspaceAccessError(f"İndekslenmiş kaynak dosya bulunamadı: {source_path}")
        reverse = self._reverse_imports(paths)
        queue = deque([(normalized, 0)])
        visited = {normalized}
        results: list[ImpactedCodeFile] = []
        while queue:
            target, distance = queue.popleft()
            if distance >= max_depth:
                continue
            for dependent, imported_via in reverse.get(target, ()):
                if dependent in visited:
                    continue
                visited.add(dependent)
                next_distance = distance + 1
                results.append(
                    ImpactedCodeFile(
                        path=dependent,
                        distance=next_distance,
                        imported_via=imported_via,
                        is_test=self._is_test_path(dependent),
                    )
                )
                queue.append((dependent, next_distance))
        results.sort(
            key=lambda item: (item.distance, not item.is_test, item.path.casefold())
        )
        return tuple(results[:max_results])

    def _reverse_imports(
        self,
        paths: tuple[str, ...],
    ) -> dict[str, tuple[tuple[str, str], ...]]:
        module_paths = self._module_paths(paths)
        reverse: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for importer in paths:
            try:
                source = self._workspace.read_text_file(importer)
                tree = ast.parse(source, filename=importer)
            except (OSError, SyntaxError, UnicodeError, ValueError, WorkspaceAccessError):
                continue
            for target, imported_via in self._resolved_imports(
                importer,
                tree,
                module_paths,
            ).items():
                if target != importer:
                    reverse[target].append((importer, imported_via))
        return {
            target: tuple(sorted(dependants, key=lambda item: item[0].casefold()))
            for target, dependants in reverse.items()
        }

    @staticmethod
    def _module_paths(paths: tuple[str, ...]) -> dict[str, str]:
        modules: dict[str, str] = {}
        for path in paths:
            module = path[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            modules[module] = path
        return modules

    def _resolved_imports(
        self,
        importer: str,
        tree: ast.AST,
        module_paths: dict[str, str],
    ) -> dict[str, str]:
        package = importer[:-3].replace("/", ".").split(".")[:-1]
        resolved: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self._record_direct_import(resolved, node, module_paths)
            elif isinstance(node, ast.ImportFrom):
                self._record_from_import(resolved, node, package, module_paths)
        return resolved

    def _record_direct_import(
        self,
        resolved: dict[str, str],
        node: ast.Import,
        module_paths: dict[str, str],
    ) -> None:
        for alias in node.names:
            self._add_module(resolved, alias.name, alias.name, module_paths)

    def _record_from_import(
        self,
        resolved: dict[str, str],
        node: ast.ImportFrom,
        package: list[str],
        module_paths: dict[str, str],
    ) -> None:
        module = self._absolute_module(node, package)
        candidates = tuple(
            f"{module}.{alias.name}" if module else alias.name
            for alias in node.names
        )
        matched = tuple(candidate for candidate in candidates if candidate in module_paths)
        for candidate in matched:
            self._add_module(resolved, candidate, candidate, module_paths)
        if not matched:
            self._add_module(resolved, module, module, module_paths)

    @staticmethod
    def _absolute_module(node: ast.ImportFrom, package: list[str]) -> str:
        if node.level < 1:
            return node.module or ""
        keep = max(0, len(package) - node.level + 1)
        suffix = (node.module or "").split(".") if node.module else []
        return ".".join((*package[:keep], *suffix))

    @staticmethod
    def _add_module(
        resolved: dict[str, str],
        module: str,
        imported_via: str,
        module_paths: dict[str, str],
    ) -> None:
        path = module_paths.get(module)
        if path is not None:
            resolved.setdefault(path, imported_via)

    @staticmethod
    def _is_test_path(path: str) -> bool:
        target = Path(path)
        directories = {part.casefold() for part in target.parts[:-1]}
        name = target.name.casefold()
        return "tests" in directories or name.startswith("test_") or name.endswith("_test.py")
