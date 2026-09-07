from boru.testing.parser import RuleBasedTestAgentRequestParser
from boru.architecture.request_parser import RuleBasedArchitectureRequestParser


class ImprovementCoordinator:
    """One explicit objective, one proposal, one confirmation; no recursive self edits."""

    _APPROVE = "iyileştirmeyi onayla"
    _UNDO = "iyileştirmeyi geri al"
    _UNDO_APPROVE = "iyileştirme geri almayı onayla"

    def __init__(
        self,
        coding,
        applier,
        evaluator,
        *,
        include_baseline_context: bool = False,
        baseline_context_characters: int = 5000,
    ):
        if baseline_context_characters < 1:
            raise ValueError("Başlangıç değerlendirme bağlamı sınırı pozitif olmalıdır.")
        self._coding = coding
        self._applier = applier
        self._evaluator = evaluator
        self._include_baseline_context = include_baseline_context
        self._baseline_context_characters = baseline_context_characters
        self._undo_pending = False

    @property
    def has_pending(self) -> bool:
        return self._undo_pending or self._coding.has_pending

    def resolve(self, message: str) -> str | None:
        normalized = " ".join(message.strip().casefold().split())
        if self._undo_pending:
            return self._resolve_undo(normalized)
        if self._coding.has_pending:
            return self._resolve_pending(normalized)
        if normalized == self._UNDO:
            if not self._applier.can_undo:
                return "Bu oturumda geri alınacak iyileştirme yok."
            self._undo_pending = True
            return ("Son iyileştirmenin dosyaları önceki içeriğe döndürülecek. "
                    f"Onay: '{self._UNDO_APPROVE}'; vazgeçmek için 'iptal'.")
        prefix, separator, value = message.partition(":")
        if prefix.strip().casefold() != "iyileştir":
            return None
        paths_text, divider, objective = value.partition("|")
        if not separator or not divider or not objective.strip():
            return "Biçim: iyileştir: boru/dosya.py[, ikinci.py] | somut iyileştirme hedefi"
        return self._prepare(paths_text, objective)

    def _prepare(self, paths_text: str, objective: str) -> str:
        try:
            request = RuleBasedTestAgentRequestParser().parse("test ajanı: " + paths_text)
            if request is None:
                raise ValueError("Dosya kapsamı boş.")
            baseline = self._evaluator.evaluate(request.source_paths)
            baseline_text = baseline.render()
            self._applier.allowed_paths = request.source_paths
            task = objective.strip()
            explicit = RuleBasedArchitectureRequestParser().parse_task(task).file_scope
            if not explicit:
                task += "\nBORU_DOSYA_KAPSAMI: " + ", ".join(request.source_paths)
            if self._include_baseline_context:
                task += (
                    "\n\nDOĞRULAMA_KANITI:\n"
                    + baseline_text[: self._baseline_context_characters]
                )
            response = self._coding.resolve("kodla: " + task)
        except (OSError, ValueError, RuntimeError) as error:
            return f"İyileştirme başlatılamadı: {error}"
        return ("İYİLEŞTİRME ÖNERİSİ\nBaşlangıç değerlendirmesi:\n" + baseline_text
                + "\n\n" + (response or "Öneri hazırlanamadı.").replace(
                    "kod değişikliğini onayla", self._APPROVE))

    def _resolve_pending(self, normalized: str) -> str:
        if normalized in {"iptal", "vazgeç"}:
            return self._coding.resolve("iptal")
        if normalized != self._APPROVE:
            return f"İyileştirme onay bekliyor: '{self._APPROVE}' veya 'iptal' yazın."
        result = self._coding.resolve("kod değişikliğini onayla")
        report = self._applier.last_validation
        if report is not None and result.startswith("Coding Agent değişikliği uygulandı"):
            result += "\n\nGeçici kopya değerlendirmesi:\n" + report.render()
        return result

    def _resolve_undo(self, normalized):
        if normalized in {"iptal", "vazgeç"}:
            self._undo_pending = False
            return "İyileştirmeyi geri alma iptal edildi."
        if normalized != self._UNDO_APPROVE:
            return f"Geri alma onay bekliyor: '{self._UNDO_APPROVE}' veya 'iptal'."
        self._undo_pending = False
        try:
            result = self._applier.rollback()
        except (OSError, RuntimeError, ValueError) as error:
            return f"İyileştirme geri alınamadı: {error}"
        return f"İyileştirme geri alındı: {len(result.outcomes)} dosya."
