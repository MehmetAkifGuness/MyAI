import re
from pathlib import Path

from boru.code_index import (
    RelatedCodeFile,
    SafeCodeImpactIndex,
    SafeCodeIndex,
    SafeCodeRelationshipIndex,
)
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
        impacts: SafeCodeImpactIndex | None = None,
        *,
        batch_runtime_repair_enabled: bool = False,
    ) -> None:
        self._base = SafeChangeScopeResolver(root, index)
        self._files = SafeProjectFileIndex(root, max_files=1000)
        self._relationships = relationships
        self._impacts = impacts
        self._batch_runtime_repair_enabled = batch_runtime_repair_enabled

    def resolve(self, objective: str) -> ChangeScope:
        scope = self._resolve_base_scope(objective)
        if scope.explicit or len(scope.paths) != 1 or not self._is_test_path(scope.paths[0]):
            return scope
        return self._expand_test_scope(scope, objective, required=False)

    def resolve_runtime_repair(self, objective: str) -> ChangeScope:
        scope = self._resolve_base_scope(objective)
        if len(scope.paths) == 1 and self._is_test_path(scope.paths[0]):
            return self._expand_test_scope(scope, objective, required=True)
        if not self._batch_runtime_repair_enabled:
            raise ValueError(
                "Çalışma zamanı onarımı mevcut ve tekil bir test dosyası gerektirir."
            )
        if not 2 <= len(scope.paths) <= 8 or not all(
            self._is_test_path(path) for path in scope.paths
        ):
            raise ValueError(
                "Çoklu çalışma zamanı onarımı 2–8 mevcut test dosyası gerektirir."
            )
        return self._expand_batch_test_scope(scope, objective)

    def _expand_batch_test_scope(
        self,
        scope: ChangeScope,
        objective: str,
    ) -> ChangeScope:
        grouped = self._group_root_causes(scope.paths, objective)
        if len(grouped) > 4:
            raise ValueError("Çoklu onarım en fazla 4 kök neden dosyasını düzenleyebilir.")

        validation_candidates, evidence = self._batch_evidence(scope, grouped)
        root_cause_groups = tuple(
            (path, tuple(test_path for test_path, _ in members))
            for path, members in grouped.items()
        )
        grouping_text = "; ".join(
            f"{path} ← {', '.join(tests)}" for path, tests in root_cause_groups
        )
        return ChangeScope(
            paths=tuple(grouped),
            evidence=tuple(evidence),
            guidance=(
                "Kök neden grupları: " + grouping_text + ". "
                "Test sözleşmelerini değiştirmeden yalnızca bu uygulama dosyalarındaki "
                "kök nedenleri düzelt"
            ),
            validation_paths=tuple(dict.fromkeys(validation_candidates))[:8],
            root_cause_groups=root_cause_groups,
        )

    def _group_root_causes(
        self,
        test_paths: tuple[str, ...],
        objective: str,
    ) -> dict[str, list[tuple[str, RelatedCodeFile]]]:
        grouped: dict[str, list[tuple[str, RelatedCodeFile]]] = {}
        for test_path in test_paths:
            implementation = self._select_implementation(test_path, objective)
            if implementation is None:
                raise ValueError(
                    f"{test_path} testinden tekil bir proje içi kök neden dosyası çıkarılamadı."
                )
            grouped.setdefault(implementation.path, []).append((test_path, implementation))
        return grouped

    def _batch_evidence(
        self,
        scope: ChangeScope,
        grouped: dict[str, list[tuple[str, RelatedCodeFile]]],
    ) -> tuple[list[str], list[str]]:
        validation_candidates = list(scope.paths)
        evidence = list(scope.evidence)
        for implementation_path, members in grouped.items():
            for test_path, relationship in members:
                evidence.append(
                    f"import ilişkisi — {test_path} → {implementation_path} "
                    f"({relationship.imported_via})"
                )
            if self._impacts is not None:
                for impact in self._impacts.impacted_files(
                    implementation_path,
                    max_depth=3,
                    max_results=12,
                ):
                    evidence.append(
                        f"ters bağımlılık — {impact.path}, mesafe {impact.distance}, "
                        f"{'test' if impact.is_test else 'çağıran'}"
                    )
                    if impact.is_test:
                        validation_candidates.append(impact.path)
        return validation_candidates, evidence

    def _expand_test_scope(
        self,
        scope: ChangeScope,
        objective: str,
        *,
        required: bool,
    ) -> ChangeScope:
        implementation = self._select_implementation(scope.paths[0], objective)
        if implementation is None:
            if required:
                raise ValueError(
                    "Testten tekil bir proje içi kök neden dosyası çıkarılamadı."
                )
            return scope
        return self._build_implementation_scope(scope, implementation, objective)

    def _resolve_base_scope(self, objective: str) -> ChangeScope:
        try:
            return self._base.resolve(objective)
        except ValueError as original_error:
            return self._resolve_file_stem(objective, original_error)

    def _select_implementation(
        self,
        primary: str,
        objective: str,
    ) -> RelatedCodeFile | None:
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
            return None
        if len(related) > 1 and related[0].score == related[1].score:
            raise ValueError(
                "Test birden fazla eşit güçlü uygulama dosyasına bağlı: "
                + ", ".join(item.path for item in related if item.score == related[0].score)
                + ". Kök neden dosyasını açıkça belirtin."
            )
        return related[0]

    def _build_implementation_scope(
        self,
        scope: ChangeScope,
        implementation: RelatedCodeFile,
        objective: str,
    ) -> ChangeScope:
        primary = scope.paths[0]
        impacts = (
            self._impacts.impacted_files(
                implementation.path,
                max_depth=3,
                max_results=12,
            )
            if self._impacts is not None
            else ()
        )
        validation_paths = tuple(
            dict.fromkeys((primary, *(item.path for item in impacts if item.is_test)))
        )[:7]
        evidence = (
            *scope.evidence,
            f"import ilişkisi — {primary} → {implementation.path} ({implementation.imported_via})",
            *(
                f"ters bağımlılık — {item.path}, mesafe {item.distance}, "
                f"{'test' if item.is_test else 'çağıran'}"
                for item in impacts
            ),
        )
        guidance = (
            f"Kök neden adayı {implementation.path} dosyasındadır. "
            f"{primary} içindeki test sözleşmesini değiştirmeden uygulama davranışını düzelt"
        )
        return ChangeScope(
            paths=(implementation.path,),
            evidence=evidence,
            guidance=guidance,
            validation_paths=validation_paths,
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
