import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.config import AppSettings
from boru.release import build_release
from boru.tasks import (
    JsonTaskCheckpointRepository,
    PersistentTaskPlanState,
    RuleBasedTaskCommandParser,
    TaskItem,
    TaskPlan,
    TaskPlanCoordinator,
    TaskStatus,
)


def task_plan():
    return TaskPlan(
        "first.py ve second.py dosyalarını güncelle",
        "Kalıcı iki adımlı plan",
        (
            TaskItem("TASK-1", "İlk", "FIRST değerini 2 yap", ("first.py",)),
            TaskItem(
                "TASK-2",
                "İkinci",
                "SECOND değerini 3 yap",
                ("second.py",),
                ("TASK-1",),
            ),
        ),
    )


class Planner:
    def plan(self, objective):
        del objective
        return task_plan()


class Workflow:
    def __init__(self):
        self.pending = False
        self.calls = []

    @property
    def has_pending(self):
        return self.pending

    def resolve(self, message):
        self.calls.append(message)
        if message.startswith("ajan görevi:"):
            self.pending = True
            return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"
        return None


class PersistentTaskStateTests(unittest.TestCase):
    def test_persists_plan_status_and_bounded_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            state = PersistentTaskPlanState(JsonTaskCheckpointRepository(path))
            state.replace_plan(task_plan())
            state.start("TASK-1")
            state.transition("TASK-1", TaskStatus.COMPLETED, "Doğrulandı")

            reloaded = PersistentTaskPlanState(JsonTaskCheckpointRepository(path))

            self.assertEqual(reloaded.get_task("TASK-1").status, TaskStatus.COMPLETED)
            self.assertEqual(reloaded.get_task("TASK-2").status, TaskStatus.PENDING)
            self.assertEqual(
                tuple(item.event for item in reloaded.get_journal()),
                ("plan_created", "task_status", "task_status"),
            )
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 1)

    def test_restart_recovers_running_task_as_pending_without_reusing_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonTaskCheckpointRepository(Path(directory) / "checkpoint.json")
            state = PersistentTaskPlanState(repository)
            state.replace_plan(task_plan())
            state.start("TASK-1")

            recovered = PersistentTaskPlanState(repository)

            task = recovered.get_task("TASK-1")
            self.assertEqual(task.status, TaskStatus.PENDING)
            self.assertIn("yeniden hazırlanmalıdır", task.note)
            self.assertEqual(recovered.get_journal()[-1].event, "task_recovered")

    def test_rejects_corrupt_and_secret_bearing_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            path.write_text('{"version": 999}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "V1"):
                PersistentTaskPlanState(JsonTaskCheckpointRepository(path))

            path.unlink()
            state = PersistentTaskPlanState(JsonTaskCheckpointRepository(path))
            unsafe = TaskPlan(
                "API değerini sk-live-1234567890123456 yap",
                "Secret testi",
                (TaskItem("TASK-1", "Secret", "Değeri değiştir", ("a.py",)),),
            )
            with self.assertRaisesRegex(ValueError, "Hassas değer"):
                state.replace_plan(unsafe)
            self.assertIsNone(state.get_plan())

    def test_failed_write_does_not_change_in_memory_plan(self):
        class FailingRepository:
            path = Path("checkpoint.json")

            def load(self):
                from boru.tasks import TaskCheckpoint

                return TaskCheckpoint(None)

            def save(self, checkpoint):
                del checkpoint
                raise RuntimeError("disk error")

        state = PersistentTaskPlanState(FailingRepository())

        with self.assertRaisesRegex(RuntimeError, "disk error"):
            state.replace_plan(task_plan())
        self.assertIsNone(state.get_plan())


class PersistentTaskCoordinatorTests(unittest.TestCase):
    def test_restored_plan_can_continue_and_journal_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonTaskCheckpointRepository(Path(directory) / "checkpoint.json")
            original = PersistentTaskPlanState(repository)
            original.replace_plan(task_plan())
            original.start("TASK-1")
            restored = PersistentTaskPlanState(repository)
            workflow = Workflow()
            coordinator = TaskPlanCoordinator(
                parser=RuleBasedTaskCommandParser(),
                planner=Planner(),
                workflow=workflow,
                state=restored,
                planned_execution_enabled=True,
            )

            journal = coordinator.resolve("görev günlüğü")
            status = coordinator.resolve("görev durumu")
            started = coordinator.resolve("planı devam ettir")

            self.assertIn("Aktif task: TASK-1", started)
            self.assertIn("task_recovered", journal)
            self.assertIn("checkpoint.json", journal)
            self.assertIn("Saklama: kalıcı checkpoint", status)
            self.assertEqual(restored.get_task("TASK-1").status, TaskStatus.RUNNING)


class ReleaseV200Tests(unittest.TestCase):
    def test_persistent_checkpoint_requires_planned_execution(self):
        with self.assertRaisesRegex(ValueError, "planlı görev"):
            main_v170.build_application(persistent_task_checkpoint_enabled=True)

    def test_default_release_enables_persistent_checkpoint(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release(), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V2.0")
            self.assertTrue(flags["planned_task_execution_enabled"])
            self.assertTrue(flags["persistent_task_checkpoint_enabled"])

    def test_checkpoint_path_can_be_configured_from_environment(self):
        with patch.dict(os.environ, {"BORU_TASK_CHECKPOINT_PATH": "data/custom_tasks.json"}):
            settings = AppSettings.from_env()

        self.assertEqual(settings.task_checkpoint_path, "data/custom_tasks.json")


if __name__ == "__main__":
    unittest.main()
