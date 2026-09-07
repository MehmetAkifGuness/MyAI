import ast
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from boru.code_index.models import (
    CodeIndexSummary,
    CodeSearchHit,
    CodeSymbol,
    CodeSymbolKind,
)
from boru.tools.project_index import SafeProjectFileIndex
from boru.tools.workspace import ReadOnlyWorkspace, WorkspaceAccessError


@dataclass(frozen=True, slots=True)
class _IndexedFile:
    fingerprint: tuple[int, int]
    lines: tuple[str, ...]
    symbols: tuple[CodeSymbol, ...]


def _walk_python_symbols(
    path: str,
    node: ast.AST,
    scope: tuple[str, ...],
    results: list[CodeSymbol],
) -> None:
    symbol_specs = _symbol_specs(node, scope)
    for name, qualified_name, kind in symbol_specs:
        results.append(
            CodeSymbol(
                path=path,
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                line=int(getattr(node, "lineno", 1)),
                end_line=int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
            )
        )
    child_scope = scope
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        child_scope = (*scope, node.name)
    for child in ast.iter_child_nodes(node):
        _walk_python_symbols(path, child, child_scope, results)


def _symbol_specs(
    node: ast.AST,
    scope: tuple[str, ...],
) -> tuple[tuple[str, str, CodeSymbolKind], ...]:
    if isinstance(node, ast.ClassDef):
        return ((node.name, ".".join((*scope, node.name)), CodeSymbolKind.CLASS),)
    if isinstance(node, ast.AsyncFunctionDef):
        return ((node.name, ".".join((*scope, node.name)), CodeSymbolKind.ASYNC_FUNCTION),)
    if isinstance(node, ast.FunctionDef):
        return ((node.name, ".".join((*scope, node.name)), CodeSymbolKind.FUNCTION),)
    if scope:
        return ()
    if isinstance(node, ast.Assign):
        names = tuple(target.id for target in node.targets if isinstance(target, ast.Name))
        return tuple((name, name, CodeSymbolKind.ASSIGNMENT) for name in names)
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return ((node.target.id, node.target.id, CodeSymbolKind.ASSIGNMENT),)
    return ()


class SafeCodeIndex:
    """Workspace sınırları içinde değişiklik-duyarlı metin ve Python sembol indeksi."""

    _TERM_PATTERN = re.compile(r"[\w.-]+", re.UNICODE)

    def __init__(
        self,
        root: str | Path,
        *,
        max_files: int = 1000,
        max_file_bytes: int = 128 * 1024,
    ) -> None:
        self._files = SafeProjectFileIndex(
            root,
            max_files=max_files,
            max_file_bytes=max_file_bytes,
        )
        self._workspace = ReadOnlyWorkspace(root, max_file_bytes=max_file_bytes)
        self._cache: dict[str, _IndexedFile] = {}

    def summary(self) -> CodeIndexSummary:
        records = self._refresh()
        suffixes = Counter(Path(path).suffix.casefold() or "(uzantısız)" for path in records)
        return CodeIndexSummary(
            file_count=len(records),
            symbol_count=sum(len(record.symbols) for record in records.values()),
            suffix_counts=tuple(sorted(suffixes.items())),
        )

    def symbols(self, relative_path: str, *, max_results: int = 100) -> tuple[CodeSymbol, ...]:
        if max_results < 1 or max_results > 200:
            raise ValueError("Sembol sonuç sınırı 1 ile 200 arasında olmalıdır.")
        normalized = relative_path.strip().replace("\\", "/")
        records = self._refresh()
        record = records.get(normalized)
        if record is None:
            raise WorkspaceAccessError(f"İndekslenmiş dosya bulunamadı: {relative_path}")
        return record.symbols[:max_results]

    def search(self, query: str, *, max_results: int = 12) -> tuple[CodeSearchHit, ...]:
        terms = self._search_terms(query, max_results)
        hits: list[CodeSearchHit] = []
        for path, record in self._refresh().items():
            hits.extend(self._symbol_hits(path, record, terms))
            hits.extend(self._line_hits(path, record, terms))
        return self._best_hits(hits, max_results)

    def _search_terms(self, query: str, max_results: int) -> tuple[str, ...]:
        if len(query) > 200:
            raise ValueError("Kod arama sorgusu en fazla 200 karakter olabilir.")
        if max_results < 1 or max_results > 30:
            raise ValueError("Kod arama sonuç sınırı 1 ile 30 arasında olmalıdır.")
        terms = tuple(dict.fromkeys(term.casefold() for term in self._TERM_PATTERN.findall(query)))
        if not terms:
            raise ValueError("Kod arama sorgusu en az bir aranabilir terim içermelidir.")
        return terms

    @staticmethod
    def _symbol_hits(
        path: str,
        record: _IndexedFile,
        terms: tuple[str, ...],
    ) -> list[CodeSearchHit]:
        hits: list[CodeSearchHit] = []
        for symbol in record.symbols:
            haystack = f"{path.casefold()} {symbol.qualified_name.casefold()}"
            matched = sum(term in haystack for term in terms)
            if not matched:
                continue
            hits.append(
                CodeSearchHit(
                    path=path,
                    line=symbol.line,
                    preview=f"{symbol.kind.value} {symbol.qualified_name}",
                    score=matched * 20 + (10 if all(term in haystack for term in terms) else 0),
                    symbol=symbol.qualified_name,
                )
            )
        return hits

    @staticmethod
    def _line_hits(
        path: str,
        record: _IndexedFile,
        terms: tuple[str, ...],
    ) -> list[CodeSearchHit]:
        hits: list[CodeSearchHit] = []
        for line_number, line in enumerate(record.lines, start=1):
            folded_line = line.casefold()
            matched = sum(term in folded_line for term in terms)
            if not matched:
                continue
            hits.append(
                CodeSearchHit(
                    path=path,
                    line=line_number,
                    preview=line.strip()[:240] or "(boş satır)",
                    score=matched * 8 + (5 if all(term in folded_line for term in terms) else 0),
                )
            )
            if len(hits) >= 3:
                break
        return hits

    @staticmethod
    def _best_hits(hits: list[CodeSearchHit], max_results: int) -> tuple[CodeSearchHit, ...]:
        hits.sort(key=lambda hit: (-hit.score, hit.path.casefold(), hit.line, hit.symbol or ""))
        unique: list[CodeSearchHit] = []
        seen: set[tuple[str, int, str]] = set()
        for hit in hits:
            key = (hit.path, hit.line, hit.preview)
            if key in seen:
                continue
            seen.add(key)
            unique.append(hit)
            if len(unique) >= max_results:
                break
        return tuple(unique)

    def _refresh(self) -> dict[str, _IndexedFile]:
        current_paths = self._files.list_editable_files()
        current_set = set(current_paths)
        for stale in set(self._cache) - current_set:
            del self._cache[stale]

        for path in current_paths:
            absolute = self._workspace.root.joinpath(*path.split("/"))
            try:
                stat = absolute.stat()
                fingerprint = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                self._cache.pop(path, None)
                continue
            cached = self._cache.get(path)
            if cached is not None and cached.fingerprint == fingerprint:
                continue
            try:
                content = self._workspace.read_text_file(path)
            except (OSError, UnicodeError, WorkspaceAccessError):
                self._cache.pop(path, None)
                continue
            self._cache[path] = _IndexedFile(
                fingerprint=fingerprint,
                lines=tuple(content.splitlines()),
                symbols=self._parse_symbols(path, content),
            )
        return dict(self._cache)

    @staticmethod
    def _parse_symbols(path: str, content: str) -> tuple[CodeSymbol, ...]:
        if not path.casefold().endswith(".py"):
            return ()
        try:
            tree = ast.parse(content, filename=path)
        except (SyntaxError, ValueError):
            return ()
        symbols: list[CodeSymbol] = []
        _walk_python_symbols(path, tree, (), symbols)
        return tuple(symbols)
