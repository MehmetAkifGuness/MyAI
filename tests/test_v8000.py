import json
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import main_v170
from boru.benchmark import BenchmarkCoordinator, BenchmarkProgress
from boru.benchmark.cases import catalog
from boru.benchmark.runner import CodingBenchmark
from boru.config import AppSettings
from boru.modeling import StructuredModelCascade, ValidatedStructuredGenerator
from boru.release import build_release
from boru.tools.project_edit import LLMProjectFileSelector
from boru.tools.project_edit_models import ProjectEditRequest
from tests.test_v6300 import executor


def response(content):
    return json.dumps({
        "action": "edit",
        "files": [{"path": "subject.py", "content": content}],
        "question": "",
    })


class AdaptiveModelTests(unittest.TestCase):
    def test_structured_retry_uses_fallback_model(self):
        primary = Mock()
        primary.generate_structured.return_value = "invalid"
        fallback = Mock()
        fallback.generate_structured.return_value = '{"value": 2}'
        cascade = StructuredModelCascade(primary, fallback)

        result = ValidatedStructuredGenerator(max_attempts=2).generate(
            cascade, [], {}, lambda raw: json.loads(raw)["value"]
        )

        self.assertEqual(result.value, 2)
        self.assertEqual(primary.generate_structured.call_count, 1)
        self.assertEqual(fallback.generate_structured.call_count, 1)

    def test_benchmark_escalates_unexpected_clarification(self):
        primary = Mock()
        primary.generate_structured.return_value = json.dumps({
            "action": "clarify", "files": [], "question": "Emin misiniz?"
        })
        fallback = Mock()
        fallback.generate_structured.return_value = response(
            "def add(a, b):\n    return a + b\n"
        )

        report = CodingBenchmark(executor).run(
            {"fast": primary}, catalog()[:1], fallback_model=("accurate", fallback)
        )

        row = report["results"][0]
        self.assertEqual(row["status"], "passed")
        self.assertEqual(row["initial_status"], "unexpected_clarification")
        self.assertEqual(row["models_used"], ["fast", "accurate"])
        self.assertEqual(row["escalations"], 1)
        self.assertEqual(report["summary"]["fast"]["human_interventions"], 0)

    def test_project_file_selection_retry_uses_fallback_model(self):
        primary = Mock()
        primary.generate_structured.return_value = '{"paths":[]}'
        fallback = Mock()
        fallback.generate_structured.return_value = '{"paths":["target.py"]}'
        selector = LLMProjectFileSelector(
            chat_model=StructuredModelCascade(primary, fallback), max_attempts=2
        )

        selected = selector.select_files(
            request=ProjectEditRequest("target davranışını düzelt"),
            available_paths=("target.py",),
        )

        self.assertEqual(selected.paths, ("target.py",))
        self.assertEqual(primary.generate_structured.call_count, 1)
        self.assertEqual(fallback.generate_structured.call_count, 1)

    def test_unexpected_clarification_counts_as_intervention_without_fallback(self):
        model = Mock()
        model.generate_structured.return_value = json.dumps({
            "action": "clarify", "files": [], "question": "Emin misiniz?"
        })

        summary = CodingBenchmark(executor).run({"model": model}, catalog()[:1])["summary"]

        self.assertEqual(summary["model"]["human_interventions"], 1)


class BenchmarkControlTests(unittest.TestCase):
    def test_reports_progress_and_stops_before_next_case(self):
        model = Mock()
        model.generate_structured.return_value = response(
            "def add(a, b):\n    return a + b\n"
        )
        cancelled = False
        progress = []

        def update(item):
            nonlocal cancelled
            progress.append(item)
            if item.completed == 1:
                cancelled = True

        report = CodingBenchmark(executor).run(
            {"model": model}, catalog()[:2], progress_callback=update,
            cancel_requested=lambda: cancelled,
        )

        self.assertEqual(report["state"], "cancelled")
        self.assertEqual(report["progress"], {"completed": 1, "total": 2})
        self.assertEqual(progress[-1].last_status, "passed")
        self.assertEqual(model.generate_structured.call_count, 1)

    def test_coordinator_status_and_cancel_produce_partial_report(self):
        entered = Event()

        class Runner:
            def run(self, models, cases, **kwargs):
                kwargs["progress_callback"](BenchmarkProgress(
                    0, 2, "fast", "addition", 1
                ))
                entered.set()
                self.assert_cancel(kwargs["cancel_requested"])
                return {"state": "cancelled", "summary": {},
                        "progress": {"completed": 0, "total": 2}}

            @staticmethod
            def assert_cancel(cancel_requested):
                tick = Event()
                for _ in range(1000):
                    if cancel_requested():
                        return
                    tick.wait(0.001)
                raise AssertionError("İptal işareti alınmadı.")

        with tempfile.TemporaryDirectory() as directory:
            coordinator = BenchmarkCoordinator(
                Path(directory), lambda repair: Runner(), lambda name: object()
            )
            coordinator.resolve("benchmark çalıştır: fast | limit=2")
            self.assertTrue(entered.wait(1))
            status = coordinator.resolve("benchmark durumu")
            cancelled = coordinator.resolve("benchmark iptal")
            coordinator._worker.join(2)
            final = coordinator.resolve("benchmark durumu")

            self.assertIn("İlerleme: 0/2", status)
            self.assertIn("fast / addition", status)
            self.assertIn("İPTAL İSTENDİ", cancelled)
            self.assertIn("İPTAL EDİLDİ", final)
            self.assertTrue(list((Path(directory) / "data" / "benchmarks").glob("*.json")))

    def test_parses_fallback_model(self):
        request = BenchmarkCoordinator._parse(
            "benchmark çalıştır: fast | yedek=accurate | limit=4"
        )
        self.assertEqual(request.models, ("fast",))
        self.assertEqual(request.fallback_model, "accurate")


class V80ReleaseTests(unittest.TestCase):
    def test_settings_reads_optional_fallback_model(self):
        with patch.dict("os.environ", {"BORU_FALLBACK_MODEL": "qwen3.5:9b"}, clear=False):
            self.assertEqual(AppSettings.from_env().fallback_model_name, "qwen3.5:9b")

    def test_v80_enables_routing_and_v70_does_not(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            build_release()
            self.assertEqual(builder.call_args.kwargs["application_version"], "V10.0")
            self.assertTrue(builder.call_args.kwargs["adaptive_model_routing_enabled"])
            build_release("V7.0")
            self.assertFalse(builder.call_args.kwargs["adaptive_model_routing_enabled"])


if __name__ == "__main__":
    unittest.main()
