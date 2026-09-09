import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main_v170
from boru.benchmark.cases import catalog
from boru.benchmark.runner import CodingBenchmark
from boru.coding.staged_applier import StagedCodingApplier
from boru.evaluation.service import EvidenceEvaluator
from boru.release import build_release
from boru.sandbox import DockerSandboxExecutor
from boru.tools.edit_models import EditProposal
from boru.tools.edit_workspace import SafeEditWorkspace
from boru.tools.project_edit_models import ProjectEditProposal, ProjectCreateSpec
from boru.tools.project_transaction import BatchProjectEditApplier
from tests.test_v1000 import TestOnlyExecutor


def executor(root):
    # Only trusted, hand-written fixtures are executed on the host in these tests.
    return TestOnlyExecutor(root, "test")


class BenchmarkTests(unittest.TestCase):
    def model(self, content="def add(a, b):\n    return a + b\n", path="subject.py"):
        return Mock(generate_structured=Mock(return_value=json.dumps({
            "action": "edit", "files": [{"path": path, "content": content}], "question": ""})))

    def test_catalog(self):
        cases = catalog()
        self.assertEqual(len(cases), 30)
        self.assertEqual(len({c.identifier for c in cases}), 30)
        for case in cases:
            for path, source in case.sources:
                compile(source, path, "exec")
            if case.action == "edit":
                self.assertTrue(case.checks)

    def test_independent_checks_and_model_comparison(self):
        good, bad = self.model(), self.model("def add(a, b):\n    return a - b\n")
        result = CodingBenchmark(executor).run({"good": good, "bad": bad}, catalog()[:1])
        self.assertEqual([r["status"] for r in result["results"]], ["passed", "failed"])
        self.assertEqual(result["summary"]["good"]["coding_passed"], 1)
        messages = good.generate_structured.call_args.args[0]
        self.assertNotIn("assertEqual", str(messages))

    def test_invalid_outputs_are_recorded_without_execution(self):
        factory = Mock()
        models = {"scope": self.model(path="../escape.py"), "syntax": self.model("return 2")}
        models["none"] = Mock(generate_structured=Mock(return_value=None))
        result = CodingBenchmark(factory).run(models, catalog()[:1])
        self.assertTrue(all(r["status"] == "validation_error" for r in result["results"]))
        factory.assert_not_called()

    def test_provider_failure_is_recorded(self):
        model = Mock(generate_structured=Mock(side_effect=TimeoutError("timeout")))
        result = CodingBenchmark(executor).run({"timeout": model}, catalog()[:1])
        self.assertEqual(result["results"][0]["status"], "model_error")

    def test_clarification_is_not_a_coding_pass(self):
        model = Mock(generate_structured=Mock(return_value=json.dumps(
            {"action": "clarify", "files": [], "question": "Hangi para birimi?"})))
        result = CodingBenchmark(executor).run({"m": model}, catalog()[-1:])
        self.assertEqual(result["results"][0]["status"], "clarification_requested")
        self.assertEqual(result["summary"]["m"]["coding_total"], 0)

    def test_budget_stops_before_request(self):
        model = self.model()
        report = CodingBenchmark(executor, clock=Mock(side_effect=[0, 2])).run(
            {"m": model}, catalog()[:1], budget_seconds=1)
        self.assertEqual(report["state"], "budget_exhausted")
        model.generate_structured.assert_not_called()


class StagedCodingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "value_test.py").write_text(
            "import unittest\nfrom value import VALUE\nclass ValueTests(unittest.TestCase):\n"
            "    def test_value(self):\n        self.assertEqual(VALUE, 2)\n", encoding="utf-8")
        self.workspace = SafeEditWorkspace(self.root)
        self.delegate = Mock(wraps=BatchProjectEditApplier(workspace=self.workspace))
        self.applier = StagedCodingApplier(self.root, self.evaluator, self.delegate)

    @staticmethod
    def evaluator(root):
        return EvidenceEvaluator(root, executor(root))

    def proposal(self, value=2, creations=()):
        source = self.workspace.read_edit_source("value.py")
        updated = f"VALUE = {value}\n"
        return ProjectEditProposal("change VALUE", (EditProposal(
            source.path, updated, source.sha256, "diff", len(source.content), len(updated)),), creations)

    def test_pass_applies_after_validation(self):
        self.applier.apply_project_edit(self.proposal())
        self.assertEqual((self.root / "value.py").read_text(), "VALUE = 2\n")
        self.delegate.apply_project_edit.assert_called_once()

    def test_failure_preserves_original_and_new_file_absence(self):
        with self.assertRaisesRegex(ValueError, "ana kaynaklar"):
            self.applier.apply_project_edit(self.proposal(3, (ProjectCreateSpec("new.py", "NEW = 1\n"),)))
        self.assertEqual((self.root / "value.py").read_text(), "VALUE = 1\n")
        self.assertFalse((self.root / "new.py").exists())
        self.delegate.apply_project_edit.assert_not_called()

    def test_unknown_does_not_write(self):
        (self.root / "value_test.py").unlink()
        with self.assertRaisesRegex(ValueError, "ana kaynaklar"):
            self.applier.apply_project_edit(self.proposal())
        self.delegate.apply_project_edit.assert_not_called()

    def test_preexisting_static_findings_do_not_block_unrelated_fix(self):
        (self.root / "value.py").write_text(
            "VALUE = 1\n\ndef legacy():\n    try:\n        return VALUE\n    except:\n        pass\n",
            encoding="utf-8",
        )
        source = self.workspace.read_edit_source("value.py")
        updated = source.content.replace("VALUE = 1", "VALUE = 2", 1)
        proposal = ProjectEditProposal("change VALUE", (EditProposal(
            source.path, updated, source.sha256, "diff", len(source.content), len(updated)
        ),))

        self.applier.apply_project_edit(proposal)

        review = next(
            check for check in self.applier.last_validation.checks
            if check.name == "Code Review"
        )
        self.assertEqual(review.verdict.value, "GEÇTİ")
        self.assertIn("Yeni bulgu yok", review.detail)

    def test_new_static_finding_still_blocks_write(self):
        source = self.workspace.read_edit_source("value.py")
        updated = "VALUE = 2\n\ndef bad(items=[]):\n    return items\n"
        proposal = ProjectEditProposal("change VALUE", (EditProposal(
            source.path, updated, source.sha256, "diff", len(source.content), len(updated)
        ),))

        with self.assertRaisesRegex(ValueError, "Geçici kopya"):
            self.applier.apply_project_edit(proposal)

        self.delegate.apply_project_edit.assert_not_called()

    def test_source_drift_rejects(self):
        proposal = self.proposal()
        (self.root / "value.py").write_text("VALUE = 9\n")
        with self.assertRaisesRegex(ValueError, "kaynak değişmiş"):
            self.applier.apply_project_edit(proposal)
        self.delegate.apply_project_edit.assert_not_called()

    def test_project_drift_during_validation_rejects(self):
        def factory(root):
            evaluator = self.evaluator(root)
            original = evaluator.evaluate
            def evaluate(paths):
                report = original(paths)
                (self.root / "value_test.py").write_text("# externally changed\n")
                return report
            evaluator.evaluate = evaluate
            return evaluator
        applier = StagedCodingApplier(self.root, factory, self.delegate)
        with self.assertRaisesRegex(ValueError, "proje/test değişti"):
            applier.apply_project_edit(self.proposal())
        self.delegate.apply_project_edit.assert_not_called()

    def test_timeout_does_not_write(self):
        applier = StagedCodingApplier(self.root, Mock(side_effect=TimeoutError()), self.delegate)
        with self.assertRaises(TimeoutError):
            applier.apply_project_edit(self.proposal())
        self.delegate.apply_project_edit.assert_not_called()

    def test_release_gate(self):
        with patch.object(main_v170, "build_application") as builder:
            build_release()
            self.assertEqual(builder.call_args.kwargs["application_version"], "V10.0")
            self.assertTrue(builder.call_args.kwargs["staged_coding_enabled"])
            build_release("V6.0")
            self.assertFalse(builder.call_args.kwargs["staged_coding_enabled"])


@unittest.skipUnless(os.environ.get("BORU_RUN_DOCKER_TESTS") == "1", "Opt-in Docker integration")
class LiveStagedCodingTests(StagedCodingTests):
    @staticmethod
    def evaluator(root):
        return EvidenceEvaluator(root, DockerSandboxExecutor(root))
