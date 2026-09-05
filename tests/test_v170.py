import json
import tempfile
import unittest
from pathlib import Path
from threading import Event

from boru.architecture import (
    ArchitecturePlan,
    ArchitecturePlanCache,
    ArchitectureRequest,
    CachingEditSourceWorkspace,
    LLMArchitectAgent,
    ProjectStatFingerprint,
)
from boru.memory import ConservativeMemoryDecisionGate
from boru.models import ChatMessage
from boru.ollama_model import OllamaChatModel
from boru.performance import (
    ModelWarmupService,
    PerformanceMonitor,
    PerformanceStatusCoordinator,
)
from boru.tools import ProjectFileSelection, SafeEditWorkspace


class PerformanceMonitorTests(unittest.TestCase):
    def test_bounds_metrics_and_reports_aggregates(self) -> None:
        monitor = PerformanceMonitor(max_metrics=2)
        monitor.record("model.chat", 1.0, True)
        monitor.record("model.chat", 3.0, False)
        monitor.record("architect.total", 2.0, True)
        monitor.increment("architect.plan_cache.hit")

        snapshot = monitor.snapshot()
        self.assertEqual(len(snapshot.metrics), 2)
        report = PerformanceStatusCoordinator(monitor).resolve("performans durumu")
        self.assertIn("PERFORMANS RAPORU", report or "")
        self.assertIn("architect.plan_cache.hit: 1", report or "")

    def test_performance_request_is_not_considered_memory(self) -> None:
        self.assertFalse(
            ConservativeMemoryDecisionGate().should_evaluate("performans durumu")
        )


class ArchitectureCacheTests(unittest.TestCase):
    @staticmethod
    def _plan(summary: str) -> ArchitecturePlan:
        from boru.architecture import ArchitectureStep

        return ArchitecturePlan(
            summary=summary,
            existing_files=("a.py",),
            new_files=(),
            steps=(ArchitectureStep("Adım", "Açıklama", ("a.py",)),),
            risks=(),
            tests=(),
            notes=(),
        )

    def test_plan_cache_normalizes_task_and_evicts_lru(self) -> None:
        monitor = PerformanceMonitor()
        cache = ArchitecturePlanCache(max_entries=1, monitor=monitor)
        first = self._plan("first")
        cache.put("  Görev   Bir ", "hash-1", first)
        self.assertIs(cache.get("görev bir", "hash-1"), first)
        cache.put("ikinci", "hash-2", self._plan("second"))
        self.assertIsNone(cache.get("görev bir", "hash-1"))

    def test_project_fingerprint_changes_with_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.py"
            target.write_text("A = 1\n", encoding="utf-8")
            provider = ProjectStatFingerprint(root)
            before = provider.build(("a.py",))
            target.write_text("A = 200\n", encoding="utf-8")
            after = provider.build(("a.py",))
            self.assertNotEqual(before, after)

    def test_source_cache_hits_then_invalidates_on_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.py"
            target.write_text("A = 1\n", encoding="utf-8")
            monitor = PerformanceMonitor()
            cached = CachingEditSourceWorkspace(
                root,
                SafeEditWorkspace(root),
                monitor=monitor,
            )
            first = cached.read_edit_source("a.py")
            second = cached.read_edit_source("a.py")
            self.assertIs(first, second)
            target.write_text("A = 200\n", encoding="utf-8")
            third = cached.read_edit_source("a.py")
            self.assertNotEqual(first.sha256, third.sha256)
            counters = dict(monitor.snapshot().counters)
            self.assertEqual(counters["architect.source_cache.hit"], 1)
            self.assertEqual(counters["architect.source_cache.miss"], 2)


class CountingSelector:
    def __init__(self) -> None:
        self.calls = 0

    def select_files(self, *, request, available_paths):
        self.calls += 1
        return ProjectFileSelection(("a.py",))


class OneFileIndex:
    def list_editable_files(self):
        return ("a.py",)


class StructuredPlanModel:
    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, messages, schema):
        del messages, schema
        self.calls += 1
        return json.dumps(
            {
                "summary": f"plan-{self.calls}",
                "existing_files": ["a.py"],
                "new_files": [],
                "steps": [{"title": "Adım", "description": "Uygula", "files": ["a.py"]}],
                "risks": [],
                "tests": ["regresyon"],
                "notes": [],
            }
        )


class NoCreationValidator:
    def validate_new_text_file(self, relative_path, content):
        raise AssertionError((relative_path, content))


class ArchitectPlanCacheIntegrationTests(unittest.TestCase):
    def test_repeated_unchanged_request_skips_selector_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.py"
            target.write_text("A = 1\n", encoding="utf-8")
            monitor = PerformanceMonitor()
            model = StructuredPlanModel()
            selector = CountingSelector()
            agent = LLMArchitectAgent(
                chat_model=model,
                file_index=OneFileIndex(),
                file_selector=selector,
                workspace=CachingEditSourceWorkspace(root, SafeEditWorkspace(root)),
                creation_validator=NoCreationValidator(),
                plan_cache=ArchitecturePlanCache(monitor=monitor),
                fingerprint_provider=ProjectStatFingerprint(root),
                performance_monitor=monitor,
            )
            request = ArchitectureRequest("özelliği planla")
            first = agent.plan(request)
            second = agent.plan(request)
            self.assertIs(first, second)
            self.assertEqual((selector.calls, model.calls), (1, 1))

            target.write_text("A = 200\n", encoding="utf-8")
            third = agent.plan(request)
            self.assertEqual(third.summary, "plan-2")
            self.assertEqual((selector.calls, model.calls), (2, 2))


class OllamaPerformanceTests(unittest.TestCase):
    def test_model_records_duration_and_keeps_model_loaded(self) -> None:
        calls = []
        warmups = []

        def fake_chat(**kwargs):
            calls.append(kwargs)
            return {"message": {"content": "ok"}}

        monitor = PerformanceMonitor()
        model = OllamaChatModel(
            "test",
            chat_client=fake_chat,
            warmup_client=lambda **kwargs: warmups.append(kwargs),
            keep_alive="15m",
            performance_monitor=monitor,
        )
        self.assertEqual(model.generate([ChatMessage("user", "merhaba")]), "ok")
        self.assertEqual(calls[0]["keep_alive"], "15m")
        self.assertEqual(monitor.snapshot().metrics[0].operation, "model.chat")
        model.warmup()
        self.assertEqual(warmups[0]["prompt"], "")
        self.assertEqual(warmups[0]["keep_alive"], "15m")

    def test_warmup_starts_only_once(self) -> None:
        completed = Event()

        class Model:
            calls = 0

            def warmup(self):
                self.calls += 1
                completed.set()

        model = Model()
        monitor = PerformanceMonitor()
        service = ModelWarmupService(model, monitor)
        self.assertTrue(service.start())
        self.assertFalse(service.start())
        self.assertTrue(completed.wait(1))
        self.assertEqual(model.calls, 1)


if __name__ == "__main__":
    unittest.main()
