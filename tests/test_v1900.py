import unittest
from unittest.mock import patch

import main_v170
from boru.architecture import ArchitecturePlan, ArchitectureStep
from boru.release import build_release
from boru.tasks import (
    ArchitectureTaskPlanner,
    InMemoryTaskPlanState,
    RuleBasedTaskCommandParser,
    TaskItem,
    TaskPlan,
    TaskPlanCoordinator,
    TaskStatus,
)


def two_step_plan():
    return TaskPlan(
        "first.py ve second.py değerlerini güncelle",
        "İki adımlı plan",
        (
            TaskItem("TASK-1", "İlk değer", "FIRST değerini 2 yap", ("first.py",)),
            TaskItem(
                "TASK-2",
                "İkinci değer",
                "SECOND değerini 3 yap",
                ("second.py",),
                ("TASK-1",),
            ),
        ),
    )


class Planner:
    def plan(self, objective):
        del objective
        return two_step_plan()


class Workflow:
    def __init__(self, outcomes=("TAMAMLANDI", "TAMAMLANDI")):
        self.pending = False
        self.outcomes = list(outcomes)
        self.calls = []

    @property
    def has_pending(self):
        return self.pending

    def resolve(self, message):
        self.calls.append(message)
        if self.pending:
            if message == "kod değişikliğini onayla":
                self.pending = False
                return f"ORKESTRATÖR RAPORU\nGenel durum: {self.outcomes.pop(0)}"
            if message == "iptal":
                self.pending = False
                return "ORKESTRATÖR RAPORU\nGenel durum: İPTAL EDİLDİ"
            return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"
        if message.startswith("ajan görevi:"):
            self.pending = True
            return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"
        return None


def coordinator(workflow=None):
    state = InMemoryTaskPlanState()
    state.replace_plan(two_step_plan())
    instance = TaskPlanCoordinator(
        parser=RuleBasedTaskCommandParser(),
        planner=Planner(),
        workflow=workflow or Workflow(),
        state=state,
        planned_execution_enabled=True,
    )
    return instance, state


class PlannedTaskExecutionTests(unittest.TestCase):
    def test_parser_recognizes_plan_run_command(self):
        command = RuleBasedTaskCommandParser().parse("planı çalıştır")

        self.assertEqual(command.action.value, "run_plan")

    def test_runs_ready_tasks_sequentially_with_separate_approvals(self):
        workflow = Workflow()
        instance, state = coordinator(workflow)

        started = instance.resolve("planı çalıştır")
        first_finished = instance.resolve("kod değişikliğini onayla")

        self.assertIn("Durum: ONAY BEKLİYOR", started)
        self.assertIn("Aktif task: TASK-1", started)
        self.assertIn("TASK-1: completed", first_finished)
        self.assertIn("SONRAKİ ADIM ONAY BEKLİYOR", first_finished)
        self.assertIn("Aktif task: TASK-2", first_finished)
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.COMPLETED)
        self.assertEqual(state.get_task("TASK-2").status, TaskStatus.RUNNING)
        self.assertIn("BORU_DOSYA_KAPSAMI: first.py", workflow.calls[0])
        self.assertIn("BORU_DOSYA_KAPSAMI: second.py", workflow.calls[2])

        completed = instance.resolve("kod değişikliğini onayla")

        self.assertIn("PLANLI GÖREV YÜRÜTME", completed)
        self.assertIn("Durum: TAMAMLANDI", completed)
        self.assertEqual(state.get_task("TASK-2").status, TaskStatus.COMPLETED)

    def test_failed_step_stops_before_dependent_task(self):
        workflow = Workflow(("BAŞARISIZ",))
        instance, state = coordinator(workflow)
        instance.resolve("planı çalıştır")

        response = instance.resolve("kod değişikliğini onayla")

        self.assertIn("Durum: DURDU", response)
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.FAILED)
        self.assertEqual(state.get_task("TASK-2").status, TaskStatus.PENDING)
        self.assertEqual(len(workflow.calls), 2)

    def test_cancel_stops_plan_and_returns_current_task_to_pending(self):
        instance, state = coordinator()
        instance.resolve("planı çalıştır")

        response = instance.resolve("iptal")

        self.assertIn("Durum: DURDU", response)
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.PENDING)

    def test_command_is_version_gated(self):
        state = InMemoryTaskPlanState()
        state.replace_plan(two_step_plan())
        instance = TaskPlanCoordinator(
            parser=RuleBasedTaskCommandParser(),
            planner=Planner(),
            workflow=Workflow(),
            state=state,
        )

        self.assertIn("etkin değil", instance.resolve("planı çalıştır"))


class ObjectiveContextPlannerTests(unittest.TestCase):
    def test_multi_step_tasks_keep_original_goal_as_context(self):
        class Architect:
            def plan(self, request):
                return ArchitecturePlan(
                    "İki dosya",
                    ("first.py", "second.py"),
                    (),
                    (
                        ArchitectureStep("İlk", "İlk dosyayı güncelle.", ("first.py",)),
                        ArchitectureStep("İkinci", "İkinci dosyayı güncelle.", ("second.py",)),
                    ),
                    (),
                    (),
                    (),
                )

        objective = "first.py FIRST=2 ve second.py SECOND=3 yap"
        plan = ArchitectureTaskPlanner(
            Architect(),
            preserve_objective_context=True,
        ).plan(objective)

        self.assertIn("Ana hedef: " + objective, plan.tasks[0].description)
        self.assertIn("Ana hedef: " + objective, plan.tasks[1].description)


class ReleaseV190Tests(unittest.TestCase):
    def test_planned_execution_requires_task_system(self):
        with self.assertRaisesRegex(ValueError, "Task/Plan"):
            main_v170.build_application(planned_task_execution_enabled=True)

    def test_v190_release_enables_planned_execution(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V1.9"), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V1.9")
            self.assertTrue(flags["planned_task_execution_enabled"])
            self.assertTrue(flags["batch_runtime_repair_enabled"])


if __name__ == "__main__":
    unittest.main()
