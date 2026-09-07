import re
from pathlib import Path

from boru.code_index import SafeCodeIndex, SafeCodeRelationshipIndex
from boru.improvement.natural import ChangeScope, SafeChangeScopeResolver
from boru.tools.project_index import SafeProjectFileIndex


class GoalDrivenChangeScopeResolver:
    """Expand a uniquely identified failing test to one likely implementation dependency."""

    _IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")

    def __init__(
        self,
        root: str | Path,
        index: SafeCodeIndex,
        relationships: SafeCodeRelationshipIndex,
    ) -> None:
        self._base = SafeChangeScopeResolver(root, index)
        self._files = SafeProjectFileIndex(root, max_files=1000)
        self._relationships = relationships

    def resolve(self, objective: str) -> ChangeScope:
        try:
            scope = self._base.resolve(objective)
        except ValueError as original_error:
            scope = self._resolve_file_stem(objective, original_error)
        if scope.explicit or len(scope.paths) != 1:
            return scope
        primary = scope.paths[0]
        if not self._is_test_path(primary):
            return scope
        related = tuple(
            item
            for item in self._relationships.related_files(
                primary,
                objective,
                max_results=4,
            )
            if not self._is_test_path(item.path)
            and Path(item.path).name != "__init__.py"
        )
        if not related:
            return scope
        if len(related) > 1 and related[0].score == related[1].score:
            raise ValueError(
                "Test birden fazla eşit güçlü uygulama dosyasına bağlı: "
                + ", ".join(item.path for item in related if item.score == related[0].score)
                + ". Kök neden dosyasını açıkça belirtin."
            )
        implementation = related[0]
        evidence = (
            *scope.evidence,
            f"import ilişkisi — {primary} → {implementation.path} ({implementation.imported_via})",
        )
        guidance = (
            f"Kök neden adayı {implementation.path} dosyasındadır. "
            f"{primary} içindeki test sözleşmesini değiştirmeden uygulama davranışını düzelt"
        )
        return ChangeScope(
            paths=(implementation.path,),
            evidence=evidence,
            guidance=guidance,
        )

    def _resolve_file_stem(self, objective: str, original_error: ValueError) -> ChangeScope:
        tokens = {
            token.casefold()
            for token in self._IDENTIFIER_PATTERN.findall(objective)
            if "_" in token or any(character.isupper() for character in token[1:])
        }
        matches = tuple(
            path
            for path in self._files.list_editable_files()
            if Path(path).stem.casefold() in tokens
        )
        if len(matches) == 1:
            path = matches[0]
            return ChangeScope(
                paths=(path,),
                evidence=(f"dosya gövdesi eşleşmesi — {Path(path).stem}, {path}",),
            )
        if len(matches) > 1:
            raise ValueError(
                "Dosya adı birden fazla güvenli yolla eşleşiyor: "
                + ", ".join(matches)
                + ". Tam yolu belirtin."
            )
        raise original_error

    @staticmethod
    def _is_test_path(path: str) -> bool:
        target = Path(path)
        folded_parts = {part.casefold() for part in target.parts[:-1]}
        name = target.name.casefold()
        return "tests" in folded_parts or name.startswith("test_") or name.endswith("_test.py")
