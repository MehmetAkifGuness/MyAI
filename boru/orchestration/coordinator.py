from threading import RLock

from boru.orchestration.contracts import CodingWorkflow
from boru.orchestration.parser import RuleBasedOrchestrationRequestParser


class AgentOrchestrator:
    """Coding workflow'u tek onaylı Architect→Test→Security→Review akışında yönetir."""

    _USAGE = "Agent Orchestrator biçimi: 'ajan görevi: yapılacak kod değişikliği'."
    _REPORT_HEADERS = (
        "TEST AGENT RAPORU",
        "SECURITY AGENT RAPORU",
        "CODE REVIEW RAPORU",
    )

    def __init__(
        self,
        *,
        parser: RuleBasedOrchestrationRequestParser,
        coding_workflow: CodingWorkflow,
    ) -> None:
        self._parser = parser
        self._coding_workflow = coding_workflow
        self._orchestrated_pending = False
        self._lock = RLock()

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return self._coding_workflow.has_pending

    def resolve(self, user_message: str) -> str | None:
        with self._lock:
            if self._coding_workflow.has_pending:
                response = self._coding_workflow.resolve(user_message)
                if not self._orchestrated_pending:
                    return response
                if self._coding_workflow.has_pending:
                    return self._render_waiting(response)
                self._orchestrated_pending = False
                return self._render_finished(response)

            try:
                request = self._parser.parse(user_message)
            except ValueError as error:
                return f"Agent Orchestrator isteği geçersiz: {error} {self._USAGE}"
            if request is None:
                if self._parser.is_orchestration_intent(user_message):
                    return self._USAGE
                return self._coding_workflow.resolve(user_message)

            response = self._coding_workflow.resolve(f"kodla: {request.task}")
            if response is None:
                return "ORKESTRATÖR RAPORU\nGenel durum: BAŞLATILAMADI"
            if self._coding_workflow.has_pending:
                self._orchestrated_pending = True
                return self._render_proposal(response)
            return self._render_start_failure(response)

    @staticmethod
    def _render_proposal(response: str) -> str:
        return (
            "ORKESTRATÖR RAPORU\n"
            "Genel durum: ONAY BEKLİYOR\n"
            "- Architect: TAMAMLANDI\n"
            "- Coding: ÖNERİ HAZIR\n"
            "- Test: BEKLİYOR\n"
            "- Security: BEKLİYOR\n"
            "- Code Review: BEKLİYOR\n\n"
            + response
        )

    @staticmethod
    def _render_waiting(response: str | None) -> str:
        return (
            "ORKESTRATÖR RAPORU\n"
            "Genel durum: ONAY BEKLİYOR\n"
            "- Architect: TAMAMLANDI\n"
            "- Coding: ONAY BEKLİYOR\n"
            "- Test: BEKLİYOR\n"
            "- Security: BEKLİYOR\n"
            "- Code Review: BEKLİYOR\n\n"
            + (response or "Coding Agent yanıt üretmedi.")
        )

    @staticmethod
    def _render_start_failure(response: str) -> str:
        architect_status = "BAŞARISIZ" if "architect" in response.casefold() else "BELİRSİZ"
        return (
            "ORKESTRATÖR RAPORU\n"
            "Genel durum: BAŞLATILAMADI\n"
            f"- Architect: {architect_status}\n"
            "- Coding: BAŞLATILAMADI\n"
            "- Test: ÇALIŞMADI\n"
            "- Security: ÇALIŞMADI\n"
            "- Code Review: ÇALIŞMADI\n\n"
            + response
        )

    @classmethod
    def _render_finished(cls, response: str | None) -> str:
        text = response or "Coding Agent yanıt üretmedi."
        folded = text.casefold()
        if "iptal edildi" in folded:
            return (
                "ORKESTRATÖR RAPORU\n"
                "Genel durum: İPTAL EDİLDİ\n"
                "- Architect: TAMAMLANDI\n"
                "- Coding: İPTAL EDİLDİ\n"
                "- Test: ÇALIŞMADI\n"
                "- Security: ÇALIŞMADI\n"
                "- Code Review: ÇALIŞMADI\n\n"
                + text
            )

        coding_status = (
            "TAMAMLANDI"
            if "coding agent değişikliği uygulandı" in folded
            else "BAŞARISIZ"
        )
        test_status = cls._extract_status(text, "TEST AGENT RAPORU")
        security_status = cls._extract_status(text, "SECURITY AGENT RAPORU")
        review_status = cls._extract_status(text, "CODE REVIEW RAPORU")
        overall = cls._overall_status(
            coding_status,
            test_status,
            security_status,
            review_status,
        )
        return (
            "ORKESTRATÖR RAPORU\n"
            f"Genel durum: {overall}\n"
            "- Architect: TAMAMLANDI\n"
            f"- Coding: {coding_status}\n"
            f"- Test: {test_status}\n"
            f"- Security: {security_status}\n"
            f"- Code Review: {review_status}\n\n"
            + text
        )

    @classmethod
    def _extract_status(cls, response: str, header: str) -> str:
        start = response.find(header)
        if start < 0:
            return "ÇALIŞMADI"
        ends = [
            response.find(other, start + len(header))
            for other in cls._REPORT_HEADERS
            if other != header and response.find(other, start + len(header)) >= 0
        ]
        section = response[start : min(ends) if ends else len(response)]
        for line in section.splitlines():
            if line.startswith("Durum:"):
                return line.partition(":")[2].strip() or "BELİRSİZ"
        return "BELİRSİZ"

    @staticmethod
    def _overall_status(
        coding_status: str,
        test_status: str,
        security_status: str,
        review_status: str,
    ) -> str:
        if coding_status != "TAMAMLANDI":
            return "BAŞARISIZ"
        if test_status in {"BAŞARISIZ", "KEŞİF BAŞARISIZ", "BAŞLATILAMADI"}:
            return "BAŞARISIZ"
        if security_status in {"TARAMA BAŞARISIZ", "BAŞLATILAMADI"}:
            return "BAŞARISIZ"
        if review_status in {"İNCELEME BAŞARISIZ", "BAŞLATILAMADI"}:
            return "BAŞARISIZ"
        if "ÇALIŞMADI" in {test_status, security_status, review_status}:
            return "BAŞARISIZ"
        if "BELİRSİZ" in {test_status, security_status, review_status}:
            return "BAŞARISIZ"
        if (
            test_status != "BAŞARILI"
            or security_status != "TEMİZ"
            or review_status != "UYGUN"
        ):
            return "İNCELEME GEREKLİ"
        return "TAMAMLANDI"
