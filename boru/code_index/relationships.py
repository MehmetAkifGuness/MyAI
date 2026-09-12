import ast
import re
from pathlib import Path

from boru.code_index.models import RelatedCodeFile
from boru.tools.project_index import SafeProjectFileIndex
from boru.tools.workspace import ReadOnlyWorkspace, WorkspaceAccessError


class SafeCodeRelationshipIndex:
    """Python importlarını proje dosyalarına çözer ve çağrı ilgisine göre sıralar."""

    _TERM_PATTERN = re.compile(r"[\w.-]{3,}", re.UNICODE)
    _QUERY_STOP_WORDS = {
        "hangi",
        "dosyada",
        "nerede",
        "nasıl",
        "nedir",
        "sınıfı",
        "metodu",
        "içinde",
    }

    def __init__(self, root: str | Path, *, max_files: int = 1000) -> None:
        self._files = SafeProjectFileIndex(root, max_files=max_files)
        self._workspace = ReadOnlyWorkspace(root)

    def related_files(
        self,
        source_path: str,
        query: str = "",
        *,
        max_results: int = 3,
    ) -> tuple[RelatedCodeFile, ...]:
        if max_results < 1 or max_results > 10:
            raise ValueError("İlişkili dosya sonuç sınırı 1 ile 10 arasında olmalıdır.")
        normalized = source_path.strip().replace("\\", "/")
        paths = self._files.list_editable_files()
        if normalized not in paths:
            raise WorkspaceAccessError(f"İndekslenmiş kaynak dosya bulunamadı: {source_path}")
        if not normalized.casefold().endswith(".py"):
            return ()

        source = self._workspace.read_text_file(normalized)
        try:
            tree = ast.parse(source, filename=normalized)
        except (SyntaxError, ValueError):
            return ()
        module_paths = self._module_paths(paths)
        dependencies = self._resolve_imports(normalized, tree, module_paths)
        calls = self._called_names(tree)
        terms = tuple(
            dict.fromkeys(
                term.casefold()
                for term in self._TERM_PATTERN.findall(query)
                if term.casefold() not in self._QUERY_STOP_WORDS
            )
        )
        related = [
            self._score_dependency(path, imported_via, calls, terms)
            for path, imported_via in dependencies.items()
            if path != normalized
        ]
        related.sort(key=lambda item: (-item.score, item.path.casefold()))
        return tuple(related[:max_results])

    @staticmethod
    def _module_paths(paths: tuple[str, ...]) -> dict[str, str]:
        modules: dict[str, str] = {}
        for path in paths:
            if not path.casefold().endswith(".py"):
                continue
            module = path[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            modules[module] = path
        return modules

    def _resolve_imports(
        self,
        source_path: str,
        tree: ast.AST,
        module_paths: dict[str, str],
    ) -> dict[str, str]:
        source_module = source_path[:-3].replace("/", ".")
        package_parts = source_module.split(".")[:-1]
        resolved: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._add_module(resolved, alias.name, alias.name, module_paths)
            elif isinstance(node, ast.ImportFrom):
                module = self._absolute_module(node, package_parts)
                self._add_from_import(resolved, module, node, module_paths)
        return resolved

    @staticmethod
    def _absolute_module(node: ast.ImportFrom, package_parts: list[str]) -> str:
        if node.level < 1:
            return node.module or ""
        keep = max(0, len(package_parts) - node.level + 1)
        prefix = package_parts[:keep]
        suffix = (node.module or "").split(".") if node.module else []
        return ".".join((*prefix, *suffix))

    def _add_from_import(
        self,
        resolved: dict[str, str],
        module: str,
        node: ast.ImportFrom,
        module_paths: dict[str, str],
    ) -> None:
        if module in module_paths:
            self._add_module(resolved, module, module, module_paths)
            return
        for alias in node.names:
            candidate = f"{module}.{alias.name}" if module else alias.name
            self._add_module(resolved, candidate, candidate, module_paths)

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
    def _extract_ast_identifiers(node: ast.AST | None) -> set[str]:
        """AST düğümü altındaki tüm tanımlayıcı ve sembol adlarını case-insensitive çıkarır."""
        names: set[str] = set()
        if node is None:
            return names
        for item in ast.walk(node):
            if isinstance(item, ast.Name):
                names.add(item.id.casefold())
            elif isinstance(item, ast.Attribute):
                names.add(item.attr.casefold())
        return names

    @classmethod
    def _called_names(cls, tree: ast.AST) -> set[str]:
        """
        AST üzerindeki çağrıları, sınıf kalıtım (bases) ilişkilerini,
        tip anotasyonlarını ve decorator referanslarını çıkarır.
        """
        names: set[str] = set()
        for node in ast.walk(tree):
            # 1. Fonksiyon ve metot çağrıları (ast.Call)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id.casefold())
                elif isinstance(node.func, ast.Attribute):
                    names.add(node.func.attr.casefold())
            # 2. Sınıf kalıtımı (bases) ve sınıf decorator'ları
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    names.update(cls._extract_ast_identifiers(base))
                for dec in node.decorator_list:
                    names.update(cls._extract_ast_identifiers(dec))
            # 3. Fonksiyon / metot tip anotasyonları ve decorator'lar
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns:
                    names.update(cls._extract_ast_identifiers(node.returns))
                all_args = (
                    list(node.args.args)
                    + list(node.args.posonlyargs)
                    + list(node.args.kwonlyargs)
                )
                if node.args.vararg and node.args.vararg.annotation:
                    names.update(cls._extract_ast_identifiers(node.args.vararg.annotation))
                if node.args.kwarg and node.args.kwarg.annotation:
                    names.update(cls._extract_ast_identifiers(node.args.kwarg.annotation))
                for arg in all_args:
                    if arg.annotation:
                        names.update(cls._extract_ast_identifiers(arg.annotation))
                for dec in node.decorator_list:
                    names.update(cls._extract_ast_identifiers(dec))
            # 4. Değişken ve alan tip anotasyonları (AnnAssign: x: MyType = ...)
            elif isinstance(node, ast.AnnAssign):
                if node.annotation:
                    names.update(cls._extract_ast_identifiers(node.annotation))
        return names

    def _score_dependency(
        self,
        path: str,
        imported_via: str,
        calls: set[str],
        terms: tuple[str, ...],
    ) -> RelatedCodeFile:
        try:
            content = self._workspace.read_text_file(path)
        except WorkspaceAccessError:
            content = ""
        folded = f"{path}\n{content}".casefold()
        defined = self._defined_symbols(path, content)
        matched_calls = tuple(sorted(calls & set(defined)))
        call_score = sum(defined[name] for name in matched_calls)
        term_score = sum(min(folded.count(term), 5) for term in terms)
        structural_penalty = (
            20
            if Path(path).stem.casefold() in {"models", "contracts", "parser", "__init__"}
            else 0
        )
        return RelatedCodeFile(
            path=path,
            score=(
                1
                + call_score
                + term_score * 5
                + (20 if term_score else 0)
                - structural_penalty
            ),
            imported_via=imported_via,
            matched_calls=matched_calls,
        )

    @staticmethod
    def _defined_symbols(path: str, content: str) -> dict[str, int]:
        try:
            tree = ast.parse(content, filename=path)
        except (SyntaxError, ValueError):
            return {}
        symbols: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols[node.name.casefold()] = 12
            elif isinstance(node, ast.ClassDef):
                symbols[node.name.casefold()] = max(symbols.get(node.name.casefold(), 0), 8)
        return symbols
