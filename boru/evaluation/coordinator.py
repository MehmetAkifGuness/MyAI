from boru.testing.parser import RuleBasedTestAgentRequestParser


class EvaluationCoordinator:
    def __init__(self, evaluator):
        self._evaluator = evaluator

    def resolve(self, message: str) -> str | None:
        text = message.strip()
        if text.casefold() == "değerlendirme durumu":
            report = self._evaluator.latest
            if report is None:
                return "Henüz değerlendirme yapılmadı."
            if not self._evaluator.is_current(report):
                return "Değerlendirme güncel değil; kaynak veya test dosyaları değişti. Yeniden değerlendirin."
            return report.render()
        prefix, separator, value = text.partition(":")
        if prefix.strip().casefold() not in {"kendini değerlendir", "öz değerlendir"}:
            return None
        if not separator or not value.strip():
            return "Biçim: kendini değerlendir: boru/modul.py[, ikinci.py]"
        try:
            request = RuleBasedTestAgentRequestParser().parse("test ajanı: " + value)
            return self._evaluator.evaluate(request.source_paths).render()
        except (ValueError, RuntimeError, OSError) as error:
            return f"Değerlendirme yapılamadı: {error}"
