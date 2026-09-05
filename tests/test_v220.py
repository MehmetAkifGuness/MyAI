import unittest

from boru.memory import ConservativeMemoryDecisionGate
from boru.orchestration import AgentOrchestrator, RuleBasedOrchestrationRequestParser
from boru.tools import ExclusiveOperationCoordinator


def completed_response(
    *,
    test_status="BAŞARILI",
    security_status="TEMİZ",
    review_status="UYGUN",
):
    return (
        "Coding Agent değişikliği uygulandı: 1 dosya\n- a.py\n\n"
        f"TEST AGENT RAPORU\nDurum: {test_status}\n\n"
        f"SECURITY AGENT RAPORU\nDurum: {security_status}\n\n"
        f"CODE REVIEW RAPORU\nDurum: {review_status}"
    )


class CodingWorkflow:
    def __init__(self, final_response=None):
        self.pending = False
        self.calls = []
        self.final_response = final_response or completed_response()

    @property
    def has_pending(self):
        return self.pending

    def resolve(self, message):
        self.calls.append(message)
        if self.pending:
            normalized = message.casefold().strip()
            if normalized == "kod değişikliğini onayla":
                self.pending = False
                return self.final_response
            if normalized == "iptal":
                self.pending = False
                return "Coding Agent önerisi iptal edildi; hiçbir dosya değiştirilmedi."
            return "Coding Agent değişikliği onay bekliyor."
        if message.startswith("kodla:"):
            if "hazırlanamaz" in message:
                return "Coding Agent önerisi hazırlanamadı: Architect başarısız."
            self.pending = True
            return "CODING AGENT ÖNERİSİ\nDiff: -1 +2"
        return None


def orchestrator(workflow=None):
    return AgentOrchestrator(
        parser=RuleBasedOrchestrationRequestParser(),
        coding_workflow=workflow or CodingWorkflow(),
    )


class OrchestrationParserTests(unittest.TestCase):
    def test_parses_agent_task(self):
        request = RuleBasedOrchestrationRequestParser().parse(
            "ajan görevi: a.py içindeki VALUE değerini 2 yap"
        )

        self.assertEqual(request.task, "a.py içindeki VALUE değerini 2 yap")

    def test_rejects_oversized_task(self):
        with self.assertRaisesRegex(ValueError, "en fazla"):
            RuleBasedOrchestrationRequestParser(max_task_characters=4).parse(
                "görev başlat: 12345"
            )

    def test_orchestration_request_is_not_memory_candidate(self):
        self.assertFalse(
            ConservativeMemoryDecisionGate().should_evaluate(
                "ajan görevi: a.py dosyasını güncelle"
            )
        )


class AgentOrchestratorTests(unittest.TestCase):
    def test_starts_coding_proposal_and_reports_waiting_phases(self):
        workflow = CodingWorkflow()
        instance = orchestrator(workflow)

        response = instance.resolve("ajan görevi: a.py içinde VALUE değerini 2 yap")

        self.assertTrue(instance.has_pending)
        self.assertEqual(
            workflow.calls,
            ["kodla: a.py içinde VALUE değerini 2 yap"],
        )
        self.assertIn("Genel durum: ONAY BEKLİYOR", response or "")
        self.assertIn("- Architect: TAMAMLANDI", response or "")
        self.assertIn("- Test: BEKLİYOR", response or "")

    def test_approval_reports_all_successful_phases(self):
        instance = orchestrator()
        instance.resolve("ajan görevi: a.py içinde VALUE değerini 2 yap")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertFalse(instance.has_pending)
        self.assertIn("Genel durum: TAMAMLANDI", response or "")
        self.assertIn("- Coding: TAMAMLANDI", response or "")
        self.assertIn("- Test: BAŞARILI", response or "")
        self.assertIn("- Security: TEMİZ", response or "")
        self.assertIn("- Code Review: UYGUN", response or "")

    def test_failed_tests_make_workflow_failed(self):
        workflow = CodingWorkflow(
            completed_response(test_status="BAŞARISIZ")
        )
        instance = orchestrator(workflow)
        instance.resolve("ajan görevi: a.py değiştir")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("Genel durum: BAŞARISIZ", response or "")
        self.assertIn("- Test: BAŞARISIZ", response or "")

    def test_security_or_review_findings_require_inspection(self):
        workflow = CodingWorkflow(
            completed_response(
                security_status="RİSK BULUNDU",
                review_status="İYİLEŞTİRME GEREKLİ",
            )
        )
        instance = orchestrator(workflow)
        instance.resolve("ajan görevi: a.py değiştir")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("Genel durum: İNCELEME GEREKLİ", response or "")
        self.assertIn("- Security: RİSK BULUNDU", response or "")

    def test_failed_security_scan_makes_workflow_failed(self):
        workflow = CodingWorkflow(
            completed_response(security_status="TARAMA BAŞARISIZ")
        )
        instance = orchestrator(workflow)
        instance.resolve("ajan görevi: a.py değiştir")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("Genel durum: BAŞARISIZ", response or "")

    def test_missing_related_tests_require_inspection(self):
        workflow = CodingWorkflow(
            completed_response(test_status="TEST BULUNAMADI")
        )
        instance = orchestrator(workflow)
        instance.resolve("ajan görevi: a.py değiştir")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("Genel durum: İNCELEME GEREKLİ", response or "")

    def test_cancel_ends_only_orchestrated_workflow(self):
        instance = orchestrator()
        instance.resolve("ajan görevi: a.py değiştir")

        response = instance.resolve("iptal")

        self.assertFalse(instance.has_pending)
        self.assertIn("Genel durum: İPTAL EDİLDİ", response or "")
        self.assertIn("- Test: ÇALIŞMADI", response or "")

    def test_direct_coding_command_remains_backward_compatible(self):
        instance = orchestrator()

        proposal = instance.resolve("kodla: a.py içinde VALUE değerini 2 yap")
        result = instance.resolve("kod değişikliğini onayla")

        self.assertEqual(proposal, "CODING AGENT ÖNERİSİ\nDiff: -1 +2")
        self.assertEqual(result, completed_response())

    def test_start_failure_does_not_leave_pending_state(self):
        instance = orchestrator()

        response = instance.resolve("ajan görevi: hazırlanamaz")

        self.assertFalse(instance.has_pending)
        self.assertIn("Genel durum: BAŞLATILAMADI", response or "")
        self.assertIn("- Architect: BAŞARISIZ", response or "")

    def test_exclusive_operation_router_sees_only_orchestrator_pending(self):
        instance = orchestrator()
        router = ExclusiveOperationCoordinator((instance,))

        router.resolve("ajan görevi: a.py değiştir")
        response = router.resolve("başka bir komut")

        self.assertIn("Genel durum: ONAY BEKLİYOR", response or "")
        self.assertNotIn("Birden fazla onay akışı", response or "")


if __name__ == "__main__":
    unittest.main()
