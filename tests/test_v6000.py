import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import main_v170
from boru.autonomy import AutonomousDevelopmentCoordinator, RuleBasedAutonomyCommandParser
from boru.coding import ControlledCodingCoordinator, RuleBasedCodingRequestParser
from boru.evaluation import EvidenceEvaluator, Verdict
from boru.memory import ConservativeMemoryDecisionGate
from boru.orchestration import AgentOrchestrator, RuleBasedOrchestrationRequestParser
from boru.release import build_release
from boru.sandbox import DockerSandboxExecutor
from boru.tasks import InMemoryTaskPlanState, TaskItem, TaskPlan, TaskPlanCoordinator, TaskStatus
from boru.tasks.parser import RuleBasedTaskCommandParser
from boru.tasks.managed_checkpoint import ManagedTaskCheckpointRepository
from boru.tasks.reliable_state import ReliableTaskPlanState
from boru.tasks.reliable_coordinator import ReliableTaskCoordinator
from boru.tasks.repair import RepairProposalGuard, TaskRepairController
from boru.tasks.source_guard import TaskSourceFingerprintGuard
from boru.tasks.workflow_guard import GuardedTaskWorkflow
from boru.testing import RelatedTestDiscovery
from boru.tools import BatchProjectEditApplier, SafeEditWorkspace, RuleBasedSmartEditRequestParser
from boru.tools.command_models import CommandExecutionResult
from tests.test_v180 import Architect, Preparer, edit_proposal
from tests.test_v1900 import Workflow, Planner
from tests.test_v5000 import FakeTasks, FakeEvaluator


class ImmediateWorkflow(Workflow):
    def resolve(self, message):
        if message.startswith("ajan görevi:") and self.outcomes:
            status = self.outcomes.pop(0)
            if status != "ONAY BEKLİYOR":
                self.calls.append(message)
                return "ORKESTRATÖR RAPORU\nGenel durum: " + status
        return super().resolve(message)


class SequentialProgressTests(unittest.TestCase):
    def build(self, outcomes):
        state = InMemoryTaskPlanState()
        state.replace_plan(TaskPlan("Üç görev", "Sıralı", tuple(
            TaskItem(f"TASK-{i}", "Düzenle", "Değeri düzelt", (f"a{i}.py",),
                     (f"TASK-{i-1}",) if i > 1 else ()) for i in range(1, 4))))
        flow = ImmediateWorkflow(outcomes)
        return TaskPlanCoordinator(parser=RuleBasedTaskCommandParser(), planner=Planner(),
                                   workflow=flow, state=state, planned_execution_enabled=True), state, flow

    def test_three_verified_noops_complete_in_one_run(self):
        coordinator, state, flow = self.build(["TAMAMLANDI"] * 3)
        response = coordinator.resolve("planı çalıştır")
        self.assertIn("Durum: TAMAMLANDI", response)
        self.assertTrue(all(task.status is TaskStatus.COMPLETED for task in state.get_plan().tasks))
        self.assertEqual(len(flow.calls), 3)

    def test_noops_advance_to_next_approval_without_applying(self):
        coordinator, state, flow = self.build(["TAMAMLANDI", "TAMAMLANDI", "ONAY BEKLİYOR"])
        response = coordinator.resolve("planı çalıştır")
        self.assertIn("ONAY BEKLİYOR", response)
        self.assertIs(state.get_task("TASK-3").status, TaskStatus.RUNNING)
        self.assertNotIn("kod değişikliğini onayla", flow.calls)

    def test_unknown_validation_blocks_dependents(self):
        coordinator, state, flow = self.build(["TAMAMLANDI", "İNCELEME GEREKLİ", "TAMAMLANDI"])
        coordinator.resolve("planı çalıştır")
        self.assertIs(state.get_task("TASK-2").status, TaskStatus.BLOCKED)
        self.assertIs(state.get_task("TASK-3").status, TaskStatus.PENDING)
        self.assertEqual(len(flow.calls), 2)

    def test_stopped_outer_report_cannot_be_overridden_by_nested_completion(self):
        tasks = FakeTasks()
        tasks.resolve = lambda message: "PLANLI GÖREV YÜRÜTME\nDurum: DURDU\nDurum: TAMAMLANDI"
        instance = AutonomousDevelopmentCoordinator(tasks, feature_level=13)
        self.assertTrue(instance.resolve("otonom sürdür").startswith("OTONOM GELİŞTİRME\nDurum: DURDU"))

    def test_failed_evaluation_cannot_be_overridden_by_pass_text_in_output(self):
        evaluator = FakeEvaluator("ÖZ DEĞERLENDİRME RAPORU\nDurum: BAŞARISIZ\nçıktı: Durum: GEÇTİ")
        instance = AutonomousDevelopmentCoordinator(FakeTasks(), evaluator=evaluator, feature_level=13)
        self.assertIn("İNCELEME GEREKLİ", instance.resolve("otonom doğrula: a.py"))


class RecordedTestExecutor:
    """Predictable executor double; integration tests below use real Docker."""
    def __init__(self, root):
        self.root = root
        self.calls = 0

    def execute(self, spec):
        self.calls += 1
        passed = (self.root / "a.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        output = "Ran 1 test in 0.001s\n" + ("OK" if passed else "FAILED (failures=1)\nAssertionError: 1 != 2")
        return CommandExecutionResult(spec, 0 if passed else 1, 0.001, output)


class RepairFixture(unittest.TestCase):
    live = False

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "a_test.py").write_text(
            "import unittest\nfrom a import VALUE\n\nclass ValueTests(unittest.TestCase):\n"
            "    def test_value(self):\n        self.assertEqual(VALUE, 2)\n", encoding="utf-8")
        self.repository = ManagedTaskCheckpointRepository(self.root / "checkpoint.json")
        self.addCleanup(self.repository.close)
        self.state = ReliableTaskPlanState(self.repository, TaskSourceFingerprintGuard(self.root))
        self.state.replace_plan(TaskPlan("VALUE değerini 2 yap", "Değeri düzelt", (
            TaskItem("TASK-1", "Değeri düzelt", "a.py içinde VALUE değerini 2 yap", ("a.py",)),)))
        self.state.start("TASK-1")
        self.state.transition("TASK-1", TaskStatus.FAILED, "[CHANGES_APPLIED] [TEST_FAILED]")
        self.executor = DockerSandboxExecutor(self.root) if self.live else RecordedTestExecutor(self.root)
        self.evaluator = EvidenceEvaluator(self.root, self.executor)
        self.guard = RepairProposalGuard(self.evaluator)
        workspace = SafeEditWorkspace(self.root)
        proposal = edit_proposal()
        self.preparer = Preparer(replace(proposal, edits=(replace(
            proposal.edits[0], expected_sha256=workspace.read_edit_source("a.py").sha256),)))
        self.deterministic = Mock()
        coding = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(), architect=Architect(), proposal_preparer=self.preparer,
            proposal_applier=BatchProjectEditApplier(workspace=workspace),
            deterministic_edit_parser=RuleBasedSmartEditRequestParser(),
            deterministic_edit_preparer=self.deterministic,
            quality_evaluator=self.evaluator, proposal_guard=self.guard)
        flow = AgentOrchestrator(parser=RuleBasedOrchestrationRequestParser(), coding_workflow=coding)
        coordinator = TaskPlanCoordinator(parser=RuleBasedTaskCommandParser(), planner=Planner(),
            workflow=GuardedTaskWorkflow(flow, self.state), state=self.state, planned_execution_enabled=True)
        repair = TaskRepairController(self.state, coordinator, self.evaluator,
                                      RelatedTestDiscovery(self.root), self.guard)
        self.admin = ReliableTaskCoordinator(coordinator, self.state, self.repository,
                                              evaluator=self.evaluator, repair=repair)
        self.autonomy = AutonomousDevelopmentCoordinator(self.admin, evaluator=self.evaluator, feature_level=13)


class RepairWorkflowTests(RepairFixture):
    def test_pending_diagnosis_recommends_start_instead_of_retry_or_repair(self):
        self.state.reset("TASK-1")
        response = self.autonomy.resolve("otonom teşhis: TASK-1")
        self.assertIn("Task henüz çalıştırılmadı", response)
        self.assertIn("otonom başlat", response)
        self.assertNotIn("otonom onar: TASK-1' kullanın", response)

    def test_exhausted_failure_recommends_new_plan(self):
        for _ in range(2):
            self.autonomy.resolve("otonom yeniden dene: TASK-1")
        response = self.autonomy.resolve("otonom teşhis: TASK-1")
        self.assertIn("Kalan deneme: 0/3", response)
        self.assertIn("yeni görev planlayın", response)
        self.assertNotIn("otonom onar: TASK-1' kullanın", response)

    def test_multiline_health_diagnosis_and_repair_run_in_order(self):
        response = self.autonomy.resolve(
            "otonom sağlık\notonom teşhis: TASK-1\notonom onar: TASK-1"
        )
        self.assertIn("PLAN SAĞLIĞI", response)
        self.assertEqual(response.count("TASK TEŞHİSİ"), 2)
        self.assertIn("ONAY BEKLİYOR", response)
        self.assertTrue(self.autonomy.has_pending)
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 1\n")

    def test_diagnosis_does_not_change_task_or_source(self):
        before = (self.root / "checkpoint.json").read_bytes()
        response = self.autonomy.resolve("otonom teşhis: TASK-1")
        self.assertIn("TASK TEŞHİSİ", response)
        self.assertIn("AssertionError", response)
        self.assertEqual((self.root / "checkpoint.json").read_bytes(), before)
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 1\n")

    def test_repair_requires_approval_then_retests_and_preserves_tests(self):
        before = (self.root / "a_test.py").read_bytes()
        response = self.autonomy.resolve("otonom onar: TASK-1")
        self.assertIn("ONAY BEKLİYOR", response)
        self.assertIn("AssertionError", self.preparer.requests[0].instruction)
        self.assertEqual(self.preparer.requests[0].existing_file_scope, ("a.py",))
        self.deterministic.prepare_smart_edit.assert_not_called()
        self.autonomy.resolve("onayla")
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 1\n")
        response = self.autonomy.resolve("kod değişikliğini onayla")
        self.assertIn("Genel durum: TAMAMLANDI", response)
        self.assertIs(self.state.get_task("TASK-1").status, TaskStatus.COMPLETED)
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 2\n")
        self.assertEqual((self.root / "a_test.py").read_bytes(), before)

    def test_changed_test_invalidates_pending_repair(self):
        self.autonomy.resolve("otonom onar: TASK-1")
        with (self.root / "a_test.py").open("a", encoding="utf-8") as stream:
            stream.write("\n# external edit\n")
        response = self.autonomy.resolve("kod değişikliğini onayla")
        self.assertIn("SOURCE_DRIFT", response)
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 1\n")
        self.assertIs(self.state.get_task("TASK-1").status, TaskStatus.FAILED)

    def test_test_patch_is_rejected_even_when_architect_includes_it(self):
        report = self.evaluator.evaluate(("a.py",))
        self.guard.activate(report, ("a.py",))
        with self.assertRaisesRegex(ValueError, "testler korunur"):
            self.guard(edit_proposal("a_test.py"))

    def test_missing_test_evidence_does_not_start_repair(self):
        (self.root / "a_test.py").unlink()
        response = self.autonomy.resolve("otonom onar: TASK-1")
        self.assertIn("Onarım hazırlanmadı", response)
        self.assertFalse(self.autonomy.has_pending)
        self.assertEqual(self.preparer.requests, [])

    def test_repair_of_test_file_task_is_rejected(self):
        task = self.state.get_task("TASK-1")
        self.state.replace_plan(TaskPlan("Test görevi", "Test", (replace(task, files=("a_test.py",)),)))
        self.assertIn("Task test dosyası içeriyor", self.autonomy.resolve("otonom onar: TASK-1"))
        self.assertEqual(self.preparer.requests, [])

    def test_cancellation_preserves_source_and_releases_guard(self):
        self.autonomy.resolve("otonom onar: TASK-1")
        self.autonomy.resolve("otonom iptal")
        self.assertIs(self.state.get_task("TASK-1").status, TaskStatus.PENDING)
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 1\n")
        self.guard(edit_proposal("outside.py"))  # No active repair restriction remains.


class RevalidationBudgetTests(RepairFixture):
    def test_interrupted_revalidation_recovers_as_failed_without_replaying(self):
        note = self.state.get_task("TASK-1").note
        self.state.transition("TASK-1", TaskStatus.PENDING, note)
        self.state.transition("TASK-1", TaskStatus.RUNNING, note)
        self.repository.close()
        reopened = ManagedTaskCheckpointRepository(self.root / "checkpoint.json")
        self.addCleanup(reopened.close)
        state = ReliableTaskPlanState(reopened, TaskSourceFingerprintGuard(self.root))
        self.assertIs(state.get_task("TASK-1").status, TaskStatus.FAILED)
        self.assertIn("[CHANGES_APPLIED]", state.get_task("TASK-1").note)
        self.assertIn("deneme 2/3", state.health())

    def test_budget_survives_checkpoint_reload(self):
        self.autonomy.resolve("otonom yeniden dene: TASK-1")
        self.autonomy.resolve("otonom yeniden dene: TASK-1")
        self.repository.close()
        reopened = ManagedTaskCheckpointRepository(self.root / "checkpoint.json")
        self.addCleanup(reopened.close)
        state = ReliableTaskPlanState(reopened, TaskSourceFingerprintGuard(self.root))
        with self.assertRaisesRegex(ValueError, "RETRY_LIMIT"):
            state.ensure_attempt_available("TASK-1")
        self.assertIs(state.get_task("TASK-1").status, TaskStatus.FAILED)

    def test_failed_revalidations_consume_budget_and_do_not_reapply(self):
        for _ in range(2):
            self.assertIn("DOĞRULAMA BAŞARISIZ", self.autonomy.resolve("otonom yeniden dene: TASK-1"))
        calls = self.executor.calls
        self.assertIn("RETRY_LIMIT", self.autonomy.resolve("otonom yeniden dene: TASK-1"))
        self.assertIn("RETRY_LIMIT", self.autonomy.resolve("otonom onar: TASK-1"))
        self.assertEqual(self.executor.calls, calls)
        self.assertEqual(self.preparer.requests, [])
        self.assertIs(self.state.get_task("TASK-1").status, TaskStatus.FAILED)
        self.assertIn("[CHANGES_APPLIED]", self.state.get_task("TASK-1").note)

    def test_stale_revalidation_does_not_mark_completed(self):
        with patch.object(self.evaluator, "is_current", return_value=False):
            response = self.autonomy.resolve("otonom yeniden dene: TASK-1")
        self.assertIn("SOURCE_DRIFT", response)
        self.assertIs(self.state.get_task("TASK-1").status, TaskStatus.FAILED)

    def test_evaluation_exception_leaves_retryable_failure(self):
        with patch.object(self.evaluator, "evaluate", side_effect=TimeoutError("test timeout")):
            response = self.autonomy.resolve("otonom yeniden dene: TASK-1")
        self.assertIn("test timeout", response)
        self.assertIs(self.state.get_task("TASK-1").status, TaskStatus.FAILED)
        self.assertIn("deneme 2/3", self.state.health())


class ReleaseTests(unittest.TestCase):
    def test_default_v60_and_previous_release_gates(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            build_release("V6.0")
            self.assertEqual(builder.call_args.kwargs["application_version"], "V6.0")
            for version, level in (("V5.0", 10), ("V5.1", 11), ("V5.2", 12), ("V6.0", 13)):
                build_release(version)
                self.assertEqual(builder.call_args.kwargs["autonomy_feature_level"], level)

    def test_new_commands_are_version_gated_and_not_memories(self):
        for command in ("otonom teşhis: TASK-1", "otonom onar: TASK-1", "otonom sağlık"):
            self.assertIsNone(RuleBasedAutonomyCommandParser(10).parse(command))
            self.assertIsNotNone(RuleBasedAutonomyCommandParser(13).parse(command))
            self.assertFalse(ConservativeMemoryDecisionGate().should_evaluate(command))


class ApplicationRoutingTests(RepairFixture):
    def test_chat_routes_new_commands_without_conversational_model(self):
        from boru.config import AppSettings

        self.repository.close()

        def repository_factory(path, **kwargs):
            repository = ManagedTaskCheckpointRepository(path, **kwargs)
            self.addCleanup(repository.close)
            return repository

        settings = AppSettings(memory_semantic_enabled=False,
                               task_checkpoint_path=str(self.root / "checkpoint.json"))
        with (
            patch.object(main_v170, "__file__", str(self.root / "main_v170.py")),
            patch.object(main_v170.AppSettings, "from_env", return_value=settings),
            patch.object(main_v170, "ManagedTaskCheckpointRepository", side_effect=repository_factory),
            patch.object(main_v170, "ChatAppUI") as ui,
            patch.object(main_v170, "OllamaChatModel") as model,
            patch.object(main_v170.ModelWarmupService, "start"),
            patch.object(main_v170.DockerSandboxExecutor, "status", return_value="SANDBOX HAZIR"),
            patch.object(main_v170.DockerSandboxExecutor, "execute", side_effect=self.executor.execute),
        ):
            build_release()
            assistant = ui.call_args.kwargs["assistant"]
            self.assertIn("otonom onar", assistant.reply("otonom yardım"))
            self.assertIn("PLAN SAĞLIĞI", assistant.reply("otonom sağlık"))
            self.assertIn("TASK TEŞHİSİ", assistant.reply("otonom teşhis: TASK-1"))
            self.assertIn("Toplam: 30", assistant.reply("benchmark görevleri"))
            model.return_value.generate.assert_not_called()



@unittest.skipUnless(os.environ.get("BORU_RUN_DOCKER_TESTS") == "1", "Opt-in Docker integration")
class LiveRepairTests(RepairFixture):
    live = True

    def test_real_sandbox_failure_approval_and_passing_retest(self):
        RepairWorkflowTests.test_repair_requires_approval_then_retests_and_preserves_tests(self)


if __name__ == "__main__":
    unittest.main()
