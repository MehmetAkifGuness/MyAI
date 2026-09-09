import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from boru.code_index import SafeCodeIndex
from boru.tools.project_index import SafeProjectFileIndex


@dataclass(frozen=True, slots=True)
class ChangeScope:
    paths: tuple[str, ...]
    evidence: tuple[str, ...]
    guidance: str = ""
    explicit: bool = False
    validation_paths: tuple[str, ...] = ()
    root_cause_groups: tuple[tuple[str, tuple[str, ...]], ...] = ()


class SafeChangeScopeResolver:
    """Resolve a natural-language change request to an unambiguous safe file scope."""

    _PATH_PATTERN = re.compile(
        r"(?<![\w./\\-])([\w.-]+(?:[/\\][\w.-]+)*\."
        r"(?:py|toml|json|ya?ml|md|txt|ini|cfg|csv|xml|html|css|js|ts|dart|java|cs|sql))"
        r"(?![\w./\\-])",
        re.IGNORECASE,
    )
    _IDENTIFIER_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
    _IGNORED_IDENTIFIERS = {
        "class",
        "dosya",
        "dosyasi",
        "dosyasinda",
        "file",
        "function",
        "metot",
        "method",
        "sinif",
        "value",
    }

    def __init__(self, root: str | Path, index: SafeCodeIndex) -> None:
        self._files = SafeProjectFileIndex(root, max_files=1000)
        self._index = index

    def resolve(self, objective: str) -> ChangeScope:
        manifest = self._files.list_editable_files()
        explicit = self._explicit_paths(objective, manifest)
        if explicit:
            return ChangeScope(
                paths=explicit,
                evidence=tuple(f"açık dosya kapsamı — {path}" for path in explicit),
                explicit=True,
            )
        return self._symbol_scope(objective)

    def _explicit_paths(self, objective: str, manifest: tuple[str, ...]) -> tuple[str, ...]:
        manifest_by_folded = {path.casefold(): path for path in manifest}
        matches: list[str] = []
        unresolved: list[str] = []
        for match in self._PATH_PATTERN.finditer(objective.replace("\\", "/")):
            candidate = match.group(1).strip("`'\"").casefold()
            exact = manifest_by_folded.get(candidate)
            if exact is not None:
                matches.append(exact)
                continue
            basename_matches = [
                path for path in manifest if Path(path).name.casefold() == candidate
            ]
            if len(basename_matches) == 1:
                matches.append(basename_matches[0])
            else:
                unresolved.append(match.group(1))
        if unresolved:
            raise ValueError(
                "İstenen dosya güvenli proje manifestinde bulunamadı veya belirsiz: "
                + ", ".join(dict.fromkeys(unresolved))
            )
        return tuple(dict.fromkeys(matches))

    def _symbol_scope(self, objective: str) -> ChangeScope:
        candidates = tuple(
            dict.fromkeys(
                token
                for token in self._IDENTIFIER_PATTERN.findall(objective)
                if self._is_symbol_candidate(token)
            )
        )
        exact_hits: dict[str, list[str]] = {}
        evidence: dict[str, str] = {}
        for candidate in candidates:
            for hit in self._index.search(candidate, max_results=20):
                if hit.symbol is None:
                    continue
                if hit.symbol.rsplit(".", 1)[-1].casefold() != candidate.casefold():
                    continue
                exact_hits.setdefault(candidate, []).append(hit.path)
                evidence.setdefault(
                    hit.path,
                    f"sembol eşleşmesi — {candidate}, {hit.path}:{hit.line}",
                )
        paths = tuple(
            dict.fromkeys(path for values in exact_hits.values() for path in values)
        )
        if len(paths) == 1:
            return ChangeScope(paths=paths, evidence=(evidence[paths[0]],))
        if len(paths) > 1:
            raise ValueError(
                "Değişiklik kapsamı birden fazla dosyayla eşleşiyor: "
                + ", ".join(paths)
                + ". Dosya yolunu açıkça belirtin."
            )
        raise ValueError(
            "Değişiklik için güvenli ve tekil dosya kapsamı bulunamadı. "
            "Mevcut dosya yolunu açıkça belirtin."
        )

    def _is_symbol_candidate(self, token: str) -> bool:
        folded = token.casefold()
        if folded in self._IGNORED_IDENTIFIERS:
            return False
        return "_" in token or token.isupper() or any(char.isupper() for char in token[1:])


class ImprovementWorkflow(Protocol):
    @property
    def has_pending(self) -> bool:
        ...

    def resolve(self, message: str) -> str | None:
        ...


@dataclass(slots=True)
class _NaturalChangeSession:
    objective: str
    scope: ChangeScope
    retry_count: int = 0
    runtime_repair: bool = False


class NaturalLanguageImprovementCoordinator:
    """Route natural code-change intent through the approved improvement workflow."""

    _APPROVE = "iyileştirmeyi onayla"
    _MUTATION_PATTERN = re.compile(
        r"\b(değiştir|düzelt|ekle|çıkar|kaldır|güncelle|yap|yeniden adlandır|refactor)\b",
        re.IGNORECASE,
    )
    _RESERVED_PREFIXES = (
        "ajan:",
        "api ",
        "bilgi ",
        "dosya oluştur:",
        "görev ",
        "git ",
        "güvenlik ",
        "kod incele:",
        "repo ",
        "github repo ",
        "kodla:",
        "mimari planla:",
        "proje bilgisi ",
        "task ",
        "test ajanı:",
        "veritabanı ",
    )

    def __init__(
        self,
        workflow: ImprovementWorkflow,
        scope_resolver: SafeChangeScopeResolver,
        *,
        max_retries: int = 1,
        runtime_repair_enabled: bool = False,
    ) -> None:
        if max_retries < 0 or max_retries > 2:
            raise ValueError("Yeniden öneri sınırı 0 ile 2 arasında olmalıdır.")
        self._workflow = workflow
        self._scope_resolver = scope_resolver
        self._max_retries = max_retries
        self._runtime_repair_enabled = runtime_repair_enabled
        self._session: _NaturalChangeSession | None = None

    @property
    def has_pending(self) -> bool:
        return self._workflow.has_pending

    def resolve(self, message: str) -> str | None:
        normalized = " ".join(message.strip().casefold().split())
        if self._workflow.has_pending:
            return self._resolve_pending(message, normalized)
        if self._is_explicit_improvement_command(normalized):
            self._session = None
            return self._workflow.resolve(message)
        runtime_repair = self._is_runtime_repair(message, normalized)
        if not runtime_repair and not self._is_natural_change_request(message, normalized):
            return None
        objective = self._runtime_objective(message) if runtime_repair else message.strip()
        try:
            scope = self._resolve_scope(objective, runtime_repair)
        except ValueError as error:
            return f"Doğal dil değişiklik isteği başlatılamadı: {error}"
        self._session = _NaturalChangeSession(
            objective=objective,
            scope=scope,
            runtime_repair=runtime_repair,
        )
        response = self._prepare(self._session)
        if not self._workflow.has_pending:
            self._session = None
        return self._render_research(scope, response, runtime_repair=runtime_repair)

    def _resolve_scope(self, objective: str, runtime_repair: bool) -> ChangeScope:
        if runtime_repair:
            resolver = getattr(self._scope_resolver, "resolve_runtime_repair", None)
            if not callable(resolver):
                raise ValueError("Çalışma zamanı kök neden çözümleyicisi etkin değil.")
            return resolver(objective)
        return self._scope_resolver.resolve(objective)

    def _resolve_pending(self, message: str, normalized: str) -> str:
        response = self._workflow.resolve(message) or "İyileştirme akışı yanıt üretmedi."
        session = self._session
        if normalized in {"iptal", "vazgeç"}:
            self._session = None
            return response
        if normalized != self._APPROVE or self._workflow.has_pending:
            return response
        if session is not None and self._is_validation_failure(response):
            if session.retry_count < self._max_retries:
                session.retry_count += 1
                retry_response = self._prepare(session, retry=True)
                if self._workflow.has_pending:
                    return response + "\n\n" + self._render_retry(session, retry_response)
            self._session = None
            return response + "\nYeniden öneri sınırına ulaşıldı; kaynak dosyalar değiştirilmedi."
        self._session = None
        return response

    def _prepare(self, session: _NaturalChangeSession, *, retry: bool = False) -> str:
        objective = session.objective
        if session.scope.guidance:
            objective += ". " + session.scope.guidance
        if retry:
            objective += (
                ". Önceki aday geçici kopya doğrulamasından geçmedi; "
                "aynı dosya kapsamında test hatasının kök nedenini gider."
            )
        paths = ", ".join(session.scope.paths)
        prepare_scoped = getattr(self._workflow, "prepare_scoped", None)
        if callable(prepare_scoped):
            return prepare_scoped(
                session.scope.paths,
                objective,
                validation_paths=session.scope.validation_paths,
            )
        return self._workflow.resolve(f"iyileştir: {paths} | {objective}") or "Öneri hazırlanamadı."

    @classmethod
    def _is_natural_change_request(cls, message: str, normalized: str) -> bool:
        if normalized.startswith(cls._RESERVED_PREFIXES):
            return False
        return cls._MUTATION_PATTERN.search(message) is not None

    def _is_runtime_repair(self, message: str, normalized: str) -> bool:
        return (
            self._runtime_repair_enabled
            and normalized.startswith("ajan:")
            and "test" in normalized
            and any(cue in normalized for cue in ("çalıştır", "calistir", "koş", "sandbox"))
            and self._MUTATION_PATTERN.search(message) is not None
        )

    @staticmethod
    def _runtime_objective(message: str) -> str:
        _, separator, objective = message.partition(":")
        return objective.strip() if separator else message.strip()

    @staticmethod
    def _is_explicit_improvement_command(normalized: str) -> bool:
        return normalized.startswith("iyileştir:") or normalized in {
            "iyileştirmeyi geri al",
            "iyileştirme geri almayı onayla",
        }

    @staticmethod
    def _is_validation_failure(response: str) -> bool:
        folded = response.casefold()
        return "uygulanamadı" in folded and (
            "değerlendirme" in folded or "doğrulama" in folded or "test" in folded
        )

    @staticmethod
    def _render_research(
        scope: ChangeScope,
        response: str,
        *,
        runtime_repair: bool = False,
    ) -> str:
        lines = [
            "ÇALIŞMA ZAMANI ONARIM AKIŞI" if runtime_repair else "DOĞAL DİL AJAN AKIŞI",
            "Durum: ARAŞTIRMA TAMAMLANDI",
            "Güvenli kapsam: " + ", ".join(scope.paths),
            *(
                ["Doğrulama kapsamı: " + ", ".join(scope.validation_paths)]
                if scope.validation_paths
                else []
            ),
            *(
                [
                    "Kök neden grupları:",
                    *(
                        f"- {implementation}: {', '.join(tests)}"
                        for implementation, tests in scope.root_cause_groups
                    ),
                ]
                if scope.root_cause_groups
                else []
            ),
            "Kanıtlar:",
            *(f"- {item}" for item in scope.evidence),
            "",
            response,
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_retry(session: _NaturalChangeSession, response: str) -> str:
        return (
            "YENİDEN ÖNERİ\n"
            f"Deneme: {session.retry_count + 1}\n"
            "Başarısız aday kaynak dosyalara uygulanmadı. Yeni aday yeniden açık onay bekliyor.\n\n"
            + response
        )
