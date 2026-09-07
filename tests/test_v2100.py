import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.release import build_release
from boru.tasks import (
    JsonTaskCheckpointRepository,
    PersistentTaskPlanState,
    TaskItem,
    TaskCheckpoint,
    TaskPlan,
    TaskSourceDriftError,
    TaskSourceFingerprintGuard,
    TaskStatus,
)


def plan() -> TaskPlan:
    return TaskPlan(
        "İki değeri güncelle",
        "Drift korumalı plan",
        (
            TaskItem("TASK-1", "İlk", "FIRST değerini 2 yap", ("first.py",)),
            TaskItem("TASK-2", "İkinci", "SECOND değerini 3 yap", ("second.py",), ("TASK-1",)),
        ),
    )


class SourceDriftStateTests(unittest.TestCase):
    def state(self, root: Path) -> PersistentTaskPlanState:
        return PersistentTaskPlanState(
            JsonTaskCheckpointRepository(root / "checkpoint.json"),
            TaskSourceFingerprintGuard(root),
        )

    def test_plan_persists_source_fingerprints_and_allows_unchanged_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.py").write_text("FIRST = 1\n", encoding="utf-8")
            (root / "second.py").write_text("SECOND = 1\n", encoding="utf-8")
            state = self.state(root)
            state.replace_plan(plan())

            started = state.start("TASK-1")
            document = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))

            self.assertEqual(started.status, TaskStatus.RUNNING)
            self.assertEqual({item["path"] for item in document["fingerprints"]}, {"first.py", "second.py"})

    def test_external_change_stops_stale_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.py").write_text("FIRST = 1\n", encoding="utf-8")
            (root / "second.py").write_text("SECOND = 1\n", encoding="utf-8")
            state = self.state(root)
            state.replace_plan(plan())
            (root / "second.py").write_text("SECOND = 99\n", encoding="utf-8")

            with self.assertRaisesRegex(TaskSourceDriftError, "second.py"):
                state.start("TASK-1")

            self.assertEqual(state.get_task("TASK-1").status, TaskStatus.PENDING)

    def test_deleted_source_stops_stale_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.py").write_text("FIRST = 1\n", encoding="utf-8")
            (root / "second.py").write_text("SECOND = 1\n", encoding="utf-8")
            state = self.state(root)
            state.replace_plan(plan())
            (root / "second.py").unlink()

            with self.assertRaisesRegex(TaskSourceDriftError, "DOSYA YOK"):
                state.start("TASK-1")

    def test_verified_completed_task_refreshes_its_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.py").write_text("FIRST = 1\n", encoding="utf-8")
            (root / "second.py").write_text("SECOND = 1\n", encoding="utf-8")
            state = self.state(root)
            state.replace_plan(plan())
            state.start("TASK-1")
            (root / "first.py").write_text("FIRST = 2\n", encoding="utf-8")
            state.transition("TASK-1", TaskStatus.COMPLETED, "Doğrulandı")

            reloaded = self.state(root)
            started = reloaded.start("TASK-2")

            self.assertEqual(started.status, TaskStatus.RUNNING)

    def test_legacy_incomplete_checkpoint_requires_replanning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.py").write_text("FIRST = 1\n", encoding="utf-8")
            (root / "second.py").write_text("SECOND = 1\n", encoding="utf-8")
            repository = JsonTaskCheckpointRepository(root / "checkpoint.json")
            repository.save(TaskCheckpoint(plan()))
            state = self.state(root)

            with self.assertRaisesRegex(TaskSourceDriftError, "yeniden planlayın"):
                state.start("TASK-1")


class ReleaseV210Tests(unittest.TestCase):
    def test_source_drift_detection_requires_persistent_checkpoint(self):
        with self.assertRaisesRegex(ValueError, "kalıcı task checkpoint"):
            main_v170.build_application(source_drift_detection_enabled=True)

    def test_default_release_enables_source_drift_detection(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V2.1"), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V2.1")
            self.assertTrue(flags["persistent_task_checkpoint_enabled"])
            self.assertTrue(flags["source_drift_detection_enabled"])
            self.assertTrue(flags["batch_runtime_repair_enabled"])


if __name__ == "__main__":
    unittest.main()
