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
    RuleBasedTaskCommandParser,
    TaskPlanCoordinator,
)


def v1_document() -> dict[str, object]:
    return {
        "version": 1,
        "plan": {
            "objective": "value.py dosyasını güncelle",
            "summary": "Eski plan",
            "tasks": [
                {
                    "task_id": "TASK-1",
                    "title": "Değeri güncelle",
                    "description": "VALUE değerini 2 yap",
                    "files": ["value.py"],
                    "dependencies": [],
                    "status": "pending",
                    "note": "",
                }
            ],
        },
        "journal": [
            {
                "sequence": 1,
                "event": "plan_created",
                "task_id": "",
                "status": "",
                "note": "Eski plan",
            }
        ],
        "fingerprints": [
            {"path": "value.py", "sha256": "a" * 64}
        ],
    }


class CheckpointMigrationTests(unittest.TestCase):
    def test_v1_is_migrated_atomically_without_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            original = v1_document()
            path.write_text(json.dumps(original), encoding="utf-8")

            checkpoint = JsonTaskCheckpointRepository(path).load()
            migrated = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(checkpoint.plan.objective, original["plan"]["objective"])
            self.assertEqual(checkpoint.journal[0].note, "Eski plan")
            self.assertEqual(checkpoint.fingerprints[0].sha256, "a" * 64)
            self.assertEqual(migrated["schema"], "boru.task-checkpoint")
            self.assertEqual(migrated["version"], 2)

    def test_migration_is_visible_in_task_journal_report(self):
        class Workflow:
            has_pending = False

            def resolve(self, message):
                del message
                return None

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            path.write_text(json.dumps(v1_document()), encoding="utf-8")
            state = PersistentTaskPlanState(JsonTaskCheckpointRepository(path))
            coordinator = TaskPlanCoordinator(
                parser=RuleBasedTaskCommandParser(),
                planner=object(),
                workflow=Workflow(),
                state=state,
            )

            report = coordinator.resolve("görev günlüğü")

            self.assertIn("boru.task-checkpoint/v2", report)
            self.assertIn("V1 → V2 migration tamamlandı", report)

    def test_invalid_legacy_document_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            raw = '{"version":1,"plan":null,"journal":[],"unexpected":true}'
            path.write_text(raw, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "desteklenen"):
                JsonTaskCheckpointRepository(path).load()

            self.assertEqual(path.read_text(encoding="utf-8"), raw)

    def test_future_schema_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            raw = '{"schema":"boru.task-checkpoint","version":99,"plan":null,"journal":[]}'
            path.write_text(raw, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "desteklenen"):
                JsonTaskCheckpointRepository(path).load()

            self.assertEqual(path.read_text(encoding="utf-8"), raw)


class ReleaseV220Tests(unittest.TestCase):
    def test_default_release_preserves_prior_features(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release(), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V2.2")
            self.assertTrue(flags["source_drift_detection_enabled"])
            self.assertTrue(flags["batch_runtime_repair_enabled"])


if __name__ == "__main__":
    unittest.main()
