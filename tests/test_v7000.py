import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main_v170
from boru.agent import ReadOnlyToolAgent
from boru.architecture import ArchitecturePlan, ArchitectureStep
from boru.code_index import RelevantFileRanker, SafeCodeIndex
from boru.coding import ControlledCodingCoordinator, RuleBasedCodingRequestParser
from boru.evaluation.models import Check, EvaluationReport, Verdict
from boru.modeling import StructuredGenerationError, ValidatedStructuredGenerator
from boru.memory import ConservativeMemoryDecisionGate
from boru.release import build_release
from boru.tools import EditOutcome, ProjectEditOutcome
from boru.tools.project_edit import LLMProjectFileSelector
from tests.test_v1100 import NoBootstrapAgent, ScriptedModel, action
from tests.test_v180 import Architect, edit_proposal


class StructuredGenerationTests(unittest.TestCase):
    def test_retries_invalid_output_with_validation_feedback(self):
        model = Mock()
        model.generate_structured.side_effect = ["bad", '{"value":2}']
        service = ValidatedStructuredGenerator(max_attempts=2)

        result = service.generate(
            model, [], {"type": "object"},
            lambda raw: json.loads(raw)["value"],
        )

        self.assertEqual(result.value, 2)
        self.assertEqual(result.attempts, 2)
        self.assertIn("VALIDATION_ERROR", model.generate_structured.call_args.args[0][-1].content)

    def test_stops_at_bounded_attempt_count(self):
        model = Mock(generate_structured=Mock(return_value="bad"))
        with self.assertRaises(StructuredGenerationError) as raised:
            ValidatedStructuredGenerator(max_attempts=2).generate(
                model, [], {}, json.loads
            )
        self.assertEqual(raised.exception.attempts, 2)
        self.assertEqual(model.generate_structured.call_count, 2)


class AgenticBenchmarkTests(unittest.TestCase):
    @staticmethod
    def _response(content):
        return json.dumps({"action": "edit", "files": [{"path": "subject.py", "content": content}],
                           "question": ""})

    def test_uses_sandbox_failure_for_one_bounded_repair(self):
        from boru.benchmark.cases import catalog
        from boru.benchmark.runner import CodingBenchmark
        from tests.test_v6300 import executor
        model = Mock()
        model.generate_structured.side_effect = [
            self._response("def add(a, b):\n    return a - b\n"),
            self._response("def add(a, b):\n    return a + b\n"),
        ]

        report = CodingBenchmark(executor).run({"model": model}, catalog()[:1])

        row = report["results"][0]
        self.assertEqual(row["status"], "passed")
        self.assertEqual(row["repair_attempts"], 1)
        self.assertEqual(row["model_calls"], 2)
        self.assertEqual(report["schema"], "boru.benchmark/v2")
        self.assertEqual(report["summary"]["model"]["coding_pass_rate"], 1.0)

    def test_repairs_structured_shape_before_sandbox(self):
        from boru.benchmark.cases import catalog
        from boru.benchmark.runner import CodingBenchmark
        from tests.test_v6300 import executor
        model = Mock()
        model.generate_structured.side_effect = [
            "not json",
            self._response("def add(a, b):\n    return a + b\n"),
        ]

        row = CodingBenchmark(executor, repair_attempts=0).run(
            {"model": model}, catalog()[:1]
        )["results"][0]

        self.assertEqual(row["status"], "passed")
        self.assertEqual(row["structured_attempts"], 2)
        self.assertEqual(len(row["structured_errors"]), 1)

    def test_accepts_fenced_json_and_ignores_nonoperative_edit_question(self):
        from boru.benchmark.cases import catalog
        from boru.benchmark.runner import CodingBenchmark
        raw = "```json\n" + json.dumps({
            "action": "edit",
            "files": [{"path": "subject.py", "content": "VALUE = 1\n"}],
            "question": "Değişiklik hazır.",
        }) + "\n```"
        action_name, files, question = CodingBenchmark._parse(raw, catalog()[:1][0])
        self.assertEqual(action_name, "edit")
        self.assertEqual(files["subject.py"], "VALUE = 1\n")
        self.assertEqual(question, "")


class ContextSelectionTests(unittest.TestCase):
    def test_ranks_symbol_and_keeps_matching_test_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payment.py").write_text("class PaymentService:\n    pass\n", encoding="utf-8")
            (root / "test_payment.py").write_text("import payment\n", encoding="utf-8")
            for index in range(50):
                (root / f"noise_{index}.py").write_text("VALUE = 1\n", encoding="utf-8")
            paths = tuple(path.name for path in root.iterdir())

            ranked = RelevantFileRanker(SafeCodeIndex(root), max_candidates=8).rank(
                "PaymentService davranışını düzelt", paths
            )

            self.assertEqual(ranked[0], "payment.py")
            self.assertIn("test_payment.py", ranked)
            self.assertLessEqual(len(ranked), 8)

    def test_llm_selector_receives_ranked_manifest(self):
        ranker = Mock()
        ranker.rank.return_value = ("target.py",)
        model = Mock(generate_structured=Mock(return_value='{"paths":["target.py"]}'))
        selector = LLMProjectFileSelector(chat_model=model, context_ranker=ranker)
        from boru.tools.project_edit_models import ProjectEditRequest

        selection = selector.select_files(
            request=ProjectEditRequest("target davranışını düzelt"),
            available_paths=("noise.py", "target.py"),
        )

        self.assertEqual(selection.paths, ("target.py",))
        self.assertNotIn("noise.py", model.generate_structured.call_args.args[0][1].content)


class FeedbackRepairTests(unittest.TestCase):
    def test_failed_staged_validation_prepares_one_bounded_repair(self):
        plan = ArchitecturePlan(
            "fix", ("a.py",), (),
            (ArchitectureStep("Fix", "Fix value", ("a.py",)),), (), ("test",), (),
        )
        architect = Architect()
        architect.plan = Mock(return_value=plan)
        first = edit_proposal()
        second = edit_proposal()
        preparer = Mock()
        preparer.prepare_project_edit.side_effect = [first, second]
        failed_report = EvaluationReport(
            ("a.py",), (), (Check("Test", Verdict.FAIL, "expected 2, got 3"),)
        )
        applier = Mock()
        applier.last_validation = failed_report
        applier.apply_project_edit.side_effect = [
            ValueError("staged test failed"),
            ProjectEditOutcome((EditOutcome("a.py", 10, 10),)),
        ]
        coordinator = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(), architect=architect,
            proposal_preparer=preparer, proposal_applier=applier,
            max_staged_repairs=1,
        )
        coordinator.resolve("kodla: a.py içinde VALUE değerini 2 yap")

        response = coordinator.resolve("kod değişikliğini onayla")

        self.assertIn("onarım önerisi", response)
        self.assertTrue(coordinator.has_pending)
        self.assertIn("DOĞRULAMA_KANITI", preparer.prepare_project_edit.call_args.args[0].instruction)
        completed = coordinator.resolve("kod değişikliğini onayla")
        self.assertIn("değişikliği uygulandı", completed)
        self.assertEqual(applier.apply_project_edit.call_count, 2)

    def test_unknown_validation_is_not_repaired(self):
        plan = ArchitecturePlan(
            "fix", ("a.py",), (),
            (ArchitectureStep("Fix", "Fix value", ("a.py",)),), (), ("test",), (),
        )
        architect = Mock(plan=Mock(return_value=plan))
        preparer = Mock(prepare_project_edit=Mock(return_value=edit_proposal()))
        applier = Mock(last_validation=EvaluationReport(
            ("a.py",), (), (Check("Test", Verdict.UNKNOWN, "test yok"),)
        ))
        applier.apply_project_edit.side_effect = ValueError("unknown")
        coordinator = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(), architect=architect,
            proposal_preparer=preparer, proposal_applier=applier,
            max_staged_repairs=1,
        )
        coordinator.resolve("kodla: a.py içinde VALUE değerini 2 yap")
        response = coordinator.resolve("kod değişikliğini onayla")
        self.assertIn("uygulanamadı", response)
        self.assertFalse(coordinator.has_pending)


class AgentRetryAndReleaseTests(unittest.TestCase):
    def test_read_only_agent_repairs_invalid_action_same_step(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "app.py").write_text("class Handler:\n    pass\n", encoding="utf-8")
            model = ScriptedModel([
                {"action": "tool"},
                action("tool", tool="search_code", arguments={"query": "Handler"}),
                action("final", answer="Handler app.py içindedir.", evidence=[1]),
            ])
            from tests.test_v1100 import ReadOnlyToolAgentTests
            helper = ReadOnlyToolAgentTests()
            runtime = helper._runtime(directory, model, max_steps=2)
            runtime._structured = ValidatedStructuredGenerator(max_attempts=2)
            report = runtime.run("Handler nerede?")
            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertEqual(len(model.prompts), 3)

    def test_v70_enables_integrated_package_and_v63_does_not(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            build_release()
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V7.0")
            self.assertTrue(flags["reliable_structured_calls_enabled"])
            self.assertTrue(flags["relevant_context_enabled"])
            self.assertTrue(flags["staged_feedback_repair_enabled"])
            self.assertTrue(flags["benchmark_chat_enabled"])
            build_release("V6.3")
            self.assertFalse(builder.call_args.kwargs["reliable_structured_calls_enabled"])


class BenchmarkCoordinatorTests(unittest.TestCase):
    def test_accepts_exact_cli_shape_and_reports_background_result(self):
        from boru.benchmark import BenchmarkCoordinator
        captured = {}

        class Runner:
            def run(self, models, cases, **kwargs):
                captured.update(models=tuple(models), cases=len(cases), kwargs=kwargs)
                return {"summary": {"qwen2.5-coder:7b": {"coding_passed": 1}}}

        with tempfile.TemporaryDirectory() as directory:
            coordinator = BenchmarkCoordinator(
                Path(directory), lambda repair: Runner(), lambda name: object()
            )
            started = coordinator.resolve(
                "python -B -m boru.benchmark --model qwen2.5-coder:7b --limit 5"
            )
            coordinator._worker.join(2)
            status = coordinator.resolve("benchmark durumu")

            self.assertIn("BAŞLATILDI", started)
            self.assertIn("TAMAMLANDI", status)
            self.assertEqual(captured["models"], ("qwen2.5-coder:7b",))
            self.assertEqual(captured["cases"], 5)
            self.assertEqual(captured["kwargs"]["repeats"], 1)
            self.assertTrue(list((Path(directory) / "data" / "benchmarks").glob("*.json")))

    def test_accepts_native_form_and_rejects_unsafe_options(self):
        from boru.benchmark import BenchmarkCoordinator
        request = BenchmarkCoordinator._parse(
            "benchmark çalıştır: qwen3.5:9b,qwen2.5-coder:7b | limit=4 | tekrar=2 | onarım=0"
        )
        self.assertEqual(request.limit, 4)
        self.assertEqual(request.repeats, 2)
        self.assertEqual(request.repair_attempts, 0)
        with self.assertRaisesRegex(ValueError, "İzin verilmeyen"):
            BenchmarkCoordinator._parse(
                "python -B -m boru.benchmark --model qwen3.5:9b --output outside.json"
            )

    def test_lists_cases_without_starting_model(self):
        from boru.benchmark import BenchmarkCoordinator
        coordinator = BenchmarkCoordinator(Path.cwd(), Mock(), Mock())
        response = coordinator.resolve("benchmark görevleri")
        self.assertIn("Toplam: 30", response)
        self.assertIn("addition [bugfix]", response)

    def test_commands_are_not_memory_candidates(self):
        gate = ConservativeMemoryDecisionGate()
        self.assertFalse(gate.should_evaluate("benchmark çalıştır: qwen3.5:9b | limit=5"))
        self.assertFalse(gate.should_evaluate(
            "python -B -m boru.benchmark --model qwen3.5:9b --limit 5"
        ))


if __name__ == "__main__":
    unittest.main()
