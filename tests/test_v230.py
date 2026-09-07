import unittest

from boru.architecture import ArchitecturePlan, ArchitectureStep
from boru.memory import ConservativeMemoryDecisionGate
from boru.tasks import (
    ArchitectureTaskPlanner,
    InMemoryTaskPlanState,
    RuleBasedTaskCommandParser,
    TaskItem,
    TaskPlan,
    TaskPlanCoordinator,
    TaskStatus,
)
from boru.tools import (
    EditSource,
    ExclusiveOperationCoordinator,
    LLMProjectEditProposalPreparer,
    ProjectEditRequest,
)


def task_plan():
    return TaskPlan(
        objective="a.py içinde VALUE değerini 2 yap",
        summary="İki adımlı güvenli plan",
        tasks=(
            TaskItem(
                "TASK-1",
                "Modeli güncelle",
                "a.py içinde VALUE değerini yalnızca bu dosyada 2 yap",
                ("a.py",),
            ),
            TaskItem(
                "TASK-2",
                "Servisi güncelle",
                "Yeni modeli servise bağla.",
                ("b.py",),
                ("TASK-1",),
            ),
        ),
    )


class Planner:
    def __init__(self, plan=None):
        self.value = plan or task_plan()
        self.calls = []

    def plan(self, objective):
        self.calls.append(objective)
        return self.value


class Workflow:
    def __init__(self, final_status="TAMAMLANDI"):
        self.pending = False
        self.final_status = final_status
        self.calls = []

    @property
    def has_pending(self):
        return self.pending

    def resolve(self, message):
        self.calls.append(message)
        if self.pending:
            if message == "kod değişikliğini onayla":
                self.pending = False
                return f"ORKESTRATÖR RAPORU\nGenel durum: {self.final_status}"
            if message == "iptal":
                self.pending = False
                return "ORKESTRATÖR RAPORU\nGenel durum: İPTAL EDİLDİ"
            return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"
        if message.startswith("ajan görevi:"):
            self.pending = True
            return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"
        return "delegated"


class AppliedFailureWorkflow(Workflow):
    def resolve(self, message):
        self.calls.append(message)
        if self.pending and message == "kod değişikliğini onayla":
            self.pending = False
            return (
                "ORKESTRATÖR RAPORU\nGenel durum: BAŞARISIZ\n"
                "- Coding: TAMAMLANDI\n- Test: BAŞARISIZ"
            )
        if message.startswith("ajan görevi:"):
            self.pending = True
            return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"
        return "delegated"


class AlreadySatisfiedWorkflow(Workflow):
    def resolve(self, message):
        self.calls.append(message)
        if message.startswith("ajan görevi:"):
            return "ORKESTRATÖR RAPORU\nGenel durum: TAMAMLANDI"
        return "delegated"


class RefreshRecordingState(InMemoryTaskPlanState):
    def __init__(self):
        super().__init__()
        self.refresh_sources = False

    def transition(self, task_id, status, note="", *, refresh_sources=False):
        self.refresh_sources = refresh_sources
        return super().transition(
            task_id,
            status,
            note,
            refresh_sources=refresh_sources,
        )


def coordinator(*, workflow=None, state=None, planner=None):
    return TaskPlanCoordinator(
        parser=RuleBasedTaskCommandParser(),
        planner=planner or Planner(),
        workflow=workflow or Workflow(),
        state=state,
    )


class TaskParserTests(unittest.TestCase):
    def test_parses_plan_run_status_and_reset_commands(self):
        parser = RuleBasedTaskCommandParser()

        self.assertEqual(parser.parse("görev planla: servis ekle").value, "servis ekle")
        self.assertEqual(parser.parse("görev durumu").action.value, "status")
        self.assertEqual(parser.parse("task çalıştır: task-2").value, "TASK-2")
        self.assertEqual(parser.parse("task sıfırla: TASK-2").action.value, "reset")
        self.assertEqual(parser.parse("task tamamla: TASK-2").action.value, "complete")

    def test_task_command_is_not_memory_candidate(self):
        gate = ConservativeMemoryDecisionGate()

        self.assertFalse(gate.should_evaluate("görev planla: yeni servis ekle"))
        self.assertFalse(gate.should_evaluate("task çalıştır: TASK-1"))


class ArchitecturePlanner:
    def __init__(self):
        self.requests = []

    def plan(self, request):
        self.requests.append(request)
        return ArchitecturePlan(
            summary="Model ve servisi güncelle.",
            existing_files=("a.py", "b.py"),
            new_files=(),
            steps=(
                ArchitectureStep("Model", "Modeli genişlet.", ("a.py",)),
                ArchitectureStep("Servis", "Servise bağla.", ("b.py",)),
            ),
            risks=(),
            tests=(),
            notes=(),
        )


class ArchitectureTaskPlannerTests(unittest.TestCase):
    def test_maps_architecture_steps_to_sequential_task_graph(self):
        architect = ArchitecturePlanner()

        plan = ArchitectureTaskPlanner(architect).plan(
            "a.py ve b.py içinde özelliği yalnızca bu dosyalarda ekle"
        )

        self.assertEqual(tuple(item.task_id for item in plan.tasks), ("TASK-1", "TASK-2"))
        self.assertEqual(plan.tasks[0].dependencies, ())
        self.assertEqual(plan.tasks[1].dependencies, ("TASK-1",))
        self.assertEqual(plan.tasks[1].files, ("b.py",))
        self.assertEqual(
            architect.requests[0].file_scope,
            ("a.py", "b.py"),
        )

    def test_single_step_preserves_exact_user_objective_for_execution(self):
        class SingleStepArchitect:
            def plan(self, request):
                return ArchitecturePlan(
                    summary="VALUE değerini güncelle.",
                    existing_files=("a.py",),
                    new_files=(),
                    steps=(
                        ArchitectureStep(
                            "Ayarı güncelle",
                            "Genel kaynak-temelli adım.",
                            ("a.py",),
                        ),
                    ),
                    risks=(),
                    tests=(),
                    notes=(),
                )

        objective = "a.py içinde VALUE değerini yalnızca bu dosyada 2 yap"

        plan = ArchitectureTaskPlanner(SingleStepArchitect()).plan(objective)

        self.assertEqual(plan.tasks[0].description, objective)


class TaskPlanStateTests(unittest.TestCase):
    def test_blocks_start_until_dependencies_are_completed(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())

        with self.assertRaisesRegex(ValueError, "TASK-1"):
            state.start("TASK-2")

        state.start("TASK-1")
        state.transition("TASK-1", TaskStatus.COMPLETED)
        started = state.start("TASK-2")

        self.assertEqual(started.status, TaskStatus.RUNNING)

    def test_failed_or_blocked_task_can_be_reset(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        state.start("TASK-1")
        state.transition("TASK-1", TaskStatus.BLOCKED, "İnceleme gerekli")

        reset = state.reset("TASK-1")

        self.assertEqual(reset.status, TaskStatus.PENDING)
        self.assertEqual(reset.note, "")


class TaskPlanCoordinatorTests(unittest.TestCase):
    def test_creates_and_renders_task_plan(self):
        planner = Planner()
        instance = coordinator(planner=planner)

        response = instance.resolve("görev planla: Özelliği geliştir")

        self.assertIn("GÖREV PLANI HAZIRLANDI", response or "")
        self.assertIn("TASK-1 [pending]", response or "")
        self.assertIn("TASK-2 [pending]", response or "")
        self.assertEqual(planner.calls, ["Özelliği geliştir"])

    def test_runs_task_through_orchestrator_and_marks_completed(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        workflow = Workflow()
        instance = coordinator(workflow=workflow, state=state)

        started = instance.resolve("task çalıştır: TASK-1")
        finished = instance.resolve("kod değişikliğini onayla")

        self.assertIn("TASK-1: running", started or "")
        self.assertIn("TASK-1: completed", finished or "")
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.COMPLETED)
        self.assertEqual(
            workflow.calls[0],
            "ajan görevi: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap",
        )

    def test_already_satisfied_task_completes_synchronously(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        instance = coordinator(workflow=AlreadySatisfiedWorkflow(), state=state)

        response = instance.resolve("task çalıştır: TASK-1")

        self.assertIn("TASK-1: completed", response or "")
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.COMPLETED)

    def test_review_required_marks_task_blocked(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        instance = coordinator(
            workflow=Workflow("İNCELEME GEREKLİ"),
            state=state,
        )
        instance.resolve("task çalıştır: TASK-1")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("TASK-1: blocked", response or "")
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.BLOCKED)

        accepted = instance.resolve("task tamamla: TASK-1")

        self.assertIn("TASK-1: completed", accepted or "")
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.COMPLETED)

    def test_failed_workflow_marks_task_failed(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        instance = coordinator(workflow=Workflow("BAŞARISIZ"), state=state)
        instance.resolve("task çalıştır: TASK-1")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("TASK-1: failed", response or "")

    def test_applied_failure_records_change_and_requests_fingerprint_refresh(self):
        state = RefreshRecordingState()
        state.replace_plan(task_plan())
        instance = coordinator(workflow=AppliedFailureWorkflow(), state=state)
        instance.resolve("task çalıştır: TASK-1")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("TASK-1: failed", response or "")
        self.assertTrue(state.refresh_sources)
        self.assertIn("[CHANGES_APPLIED]", state.get_task("TASK-1").note)
        self.assertIn("[TEST_FAILED]", state.get_task("TASK-1").note)

    def test_cancel_returns_running_task_to_pending(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        instance = coordinator(state=state)
        instance.resolve("task çalıştır: TASK-1")

        response = instance.resolve("iptal")

        self.assertIn("TASK-1: pending", response or "")
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.PENDING)

    def test_status_reports_progress_and_notes(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        state.start("TASK-1")
        state.transition("TASK-1", TaskStatus.COMPLETED, "Bitti")

        response = coordinator(state=state).resolve("görev durumu")

        self.assertIn("İlerleme: 1/2 tamamlandı", response or "")
        self.assertIn("Not: Bitti", response or "")

    def test_status_and_journal_remain_readable_while_approval_is_pending(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(task_plan())
        workflow = Workflow()
        instance = coordinator(workflow=workflow, state=state)
        instance.resolve("task çalıştır: TASK-1")

        status = instance.resolve("görev durumu")
        journal = instance.resolve("görev günlüğü")

        self.assertIn("TASK-1 [running]", status or "")
        self.assertIn("GÖREV GÜNLÜĞÜ", journal or "")
        self.assertTrue(workflow.has_pending)
        self.assertEqual(len(workflow.calls), 1)

    def test_unrelated_message_is_delegated_for_backward_compatibility(self):
        workflow = Workflow()

        response = coordinator(workflow=workflow).resolve("kodla: a.py değiştir")

        self.assertEqual(response, "delegated")
        self.assertEqual(workflow.calls, ["kodla: a.py değiştir"])


class ExplicitScopeManifestRegressionTests(unittest.TestCase):
    def test_project_edit_reads_architect_scope_even_when_index_is_truncated(self):
        class Model:
            def generate_structured(self, messages, schema):
                del messages, schema
                return (
                    '{"patches":[{"path":"late.py","old_text":"VALUE = 1",'
                    '"new_text":"VALUE = 2","reason":"Güncelle"}],"creates":[]}'
                )

        class TruncatedIndex:
            def list_editable_files(self):
                raise AssertionError("Açık Architect kapsamında manifest okunmamalı.")

        class Selector:
            def select_files(self, *, request, available_paths):
                raise AssertionError((request, available_paths))

        class Workspace:
            def read_edit_source(self, path):
                self.path = path
                return EditSource(path, "VALUE = 1\n", "hash")

        proposal = LLMProjectEditProposalPreparer(
            chat_model=Model(),
            file_index=TruncatedIndex(),
            file_selector=Selector(),
            workspace=Workspace(),
            max_attempts=1,
        ).prepare_project_edit(
            ProjectEditRequest("VALUE değerini 2 yap", ("late.py",), ())
        )

        self.assertEqual(proposal.edits[0].path, "late.py")

    def test_orphan_approval_is_stopped_before_other_resolvers(self):
        class Resolver:
            has_pending = False

            def resolve(self, message):
                raise AssertionError(message)

        response = ExclusiveOperationCoordinator((Resolver(),)).resolve(
            "kod değişikliğini onayla"
        )

        self.assertEqual(response, "Onay veya iptal bekleyen etkin bir işlem yok.")


if __name__ == "__main__":
    unittest.main()
