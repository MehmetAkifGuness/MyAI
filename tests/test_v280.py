import tempfile
import unittest
from pathlib import Path

from boru.evaluation import Check, EvaluationCoordinator, EvaluationReport, EvidenceEvaluator, Verdict
from boru.tools.command_models import CommandExecutionResult


class EvidenceExecutor:
    def __init__(self, output="Ran 2 tests in 0.001s\n\nOK", exit_code=0):
        self.output = output
        self.exit_code = exit_code

    def execute(self, spec):
        return CommandExecutionResult(spec, self.exit_code, 0.1, self.output)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests/test_a.py").write_text(
            "import unittest\nimport a\nclass Values(unittest.TestCase):\n"
            "    def test_value(self):\n        self.assertEqual(a.VALUE, 1)\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_positive_tests_and_static_evidence_are_required(self):
        evaluator = EvidenceEvaluator(self.root, EvidenceExecutor())
        self.assertIs(evaluator.evaluate(("a.py",)).verdict, Verdict.PASS)
        failing = EvidenceEvaluator(self.root, EvidenceExecutor("Ran 2 tests\nFAILED (failures=1)", 1))
        self.assertIs(failing.evaluate(("a.py",)).verdict, Verdict.FAIL)

    def test_missing_skipped_or_unavailable_tests_are_not_success(self):
        for output, code in (("OK", 0), ("Ran 0 tests\nOK", 0),
                             ("Ran 2 tests\nOK (skipped=2)", 0), ("Docker unavailable", 125)):
            with self.subTest(output=output):
                report = EvidenceEvaluator(self.root, EvidenceExecutor(output, code)).evaluate(("a.py",))
                self.assertIsNot(report.verdict, Verdict.PASS)

    def test_security_finding_fails_even_when_tests_pass(self):
        (self.root / "a.py").write_text("def unsafe(value):\n    return eval(value)\n", encoding="utf-8")
        report = EvidenceEvaluator(self.root, EvidenceExecutor()).evaluate(("a.py",))
        self.assertIs(report.verdict, Verdict.FAIL)
        self.assertIn("PY-EVAL-EXEC", report.render())

    def test_no_related_tests_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
            report = EvidenceEvaluator(root, EvidenceExecutor()).evaluate(("a.py",))
            self.assertIs(report.verdict, Verdict.UNKNOWN)
            self.assertIn("İlişkili test bulunamadı", report.render())

    def test_changed_test_invalidates_previous_report(self):
        evaluator = EvidenceEvaluator(self.root, EvidenceExecutor())
        evaluator.evaluate(("a.py",))
        (self.root / "tests/test_a.py").write_text("# changed", encoding="utf-8")
        self.assertIn("güncel değil", EvaluationCoordinator(evaluator).resolve("değerlendirme durumu"))

    def test_integrity_failure_blocks_orchestrator_success(self):
        checks = tuple(Check(name, Verdict.PASS, "ok") for name in ("Test", "Security", "Code Review"))
        report = EvaluationReport(("a.py",), (), checks + (Check("Kaynak bütünlüğü", Verdict.UNKNOWN, "changed"),))
        self.assertIn("TEST AGENT RAPORU\nDurum: BAŞARISIZ", report.workflow_report())


if __name__ == "__main__":
    unittest.main()
