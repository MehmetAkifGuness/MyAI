import tempfile
import unittest
from pathlib import Path

from boru.architecture import ArchitecturePlan, ArchitectureStep
from boru.coding import ControlledCodingCoordinator, RuleBasedCodingRequestParser
from boru.memory import ConservativeMemoryDecisionGate
from boru.reviewing import (
    CodeReviewAgent,
    CodeReviewReport,
    PythonCodeReviewScanner,
    ReviewFinding,
    ReviewSeverity,
    RuleBasedCodeReviewRequestParser,
)
from boru.tools import EditOutcome, EditProposal, ProjectEditOutcome, ProjectEditProposal


class CodeReviewParserTests(unittest.TestCase):
    def test_parses_multiple_paths(self):
        request = RuleBasedCodeReviewRequestParser().parse(
            "kod incele: boru/service.py, boru/models.py"
        )

        self.assertEqual(request.paths, ("boru/service.py", "boru/models.py"))

    def test_rejects_duplicate_paths(self):
        with self.assertRaisesRegex(ValueError, "birden fazla"):
            RuleBasedCodeReviewRequestParser().parse("review: a.py, A.py")

    def test_review_request_is_not_memory_candidate(self):
        self.assertFalse(
            ConservativeMemoryDecisionGate().should_evaluate(
                "kod incele: boru/service.py"
            )
        )


class PythonCodeReviewScannerTests(unittest.TestCase):
    def test_detects_maintainability_and_error_flow_problems(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "poor.py"
            target.write_text(
                "def BadName(a, b, c, d, e, f, g, h, items=[]):\n"
                "    try:\n"
                "        return len(items)\n"
                "    except:\n"
                "        pass\n"
                "    return 1\n"
                "    print('unreachable')\n",
                encoding="utf-8",
            )

            report = PythonCodeReviewScanner(directory).scan(("poor.py",))

            rules = {finding.rule for finding in report.findings}
            self.assertTrue(
                {
                    "REVIEW-BROAD-EXCEPT",
                    "REVIEW-FUNCTION-NAMING",
                    "REVIEW-MANY-PARAMETERS",
                    "REVIEW-MUTABLE-DEFAULT",
                    "REVIEW-SILENT-EXCEPT",
                    "REVIEW-UNREACHABLE-CODE",
                }.issubset(rules)
            )

    def test_detects_complex_and_deep_function_with_configured_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "complex.py"
            target.write_text(
                "def calculate(value):\n"
                "    if value:\n"
                "        for item in value:\n"
                "            if item:\n"
                "                while item:\n"
                "                    item -= 1\n"
                "    return value\n",
                encoding="utf-8",
            )

            report = PythonCodeReviewScanner(
                directory,
                max_complexity=3,
                max_nesting=3,
            ).scan(("complex.py",))

            rules = {finding.rule for finding in report.findings}
            self.assertIn("REVIEW-COMPLEX-FUNCTION", rules)
            self.assertIn("REVIEW-DEEP-NESTING", rules)

    def test_detects_exact_duplicate_function_bodies_across_files(self):
        source = (
            "def {name}(value):\n"
            "    normalized = value.strip()\n"
            "    lowered = normalized.lower()\n"
            "    return lowered\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text(source.format(name="first"), encoding="utf-8")
            (root / "b.py").write_text(source.format(name="second"), encoding="utf-8")

            report = PythonCodeReviewScanner(directory).scan(("a.py", "b.py"))

            self.assertIn(
                "REVIEW-DUPLICATE-CODE",
                {finding.rule for finding in report.findings},
            )

    def test_clean_small_function_has_no_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "clean.py"
            target.write_text(
                "def normalized_name(value: str) -> str:\n"
                "    return value.strip().casefold()\n",
                encoding="utf-8",
            )

            report = PythonCodeReviewScanner(directory).scan(("clean.py",))

            self.assertEqual(report.findings, ())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "Workspace dışına"):
                PythonCodeReviewScanner(directory).scan(("../outside.py",))


class StaticScanner:
    def __init__(self, report):
        self.report = report
        self.calls = []

    def scan(self, paths):
        self.calls.append(paths)
        return self.report


class CodeReviewCoordinatorTests(unittest.TestCase):
    def test_reports_clean_review(self):
        scanner = StaticScanner(CodeReviewReport(("a.py",), ()))
        response = CodeReviewAgent(
            parser=RuleBasedCodeReviewRequestParser(),
            scanner=scanner,
        ).resolve("code review: a.py")

        self.assertIn("Durum: UYGUN", response or "")
        self.assertEqual(scanner.calls, [("a.py",)])

    def test_reports_findings_by_severity(self):
        finding = ReviewFinding(
            "a.py",
            4,
            "REVIEW-MUTABLE-DEFAULT",
            ReviewSeverity.ERROR,
            "Mutable default",
            "None kullan",
        )
        response = CodeReviewAgent(
            parser=RuleBasedCodeReviewRequestParser(),
            scanner=StaticScanner(CodeReviewReport(("a.py",), (finding,))),
        ).review_paths(("a.py",))

        self.assertIn("Durum: İYİLEŞTİRME GEREKLİ", response)
        self.assertIn("ERROR=1", response)

    def test_does_not_report_non_python_file_as_approved(self):
        response = CodeReviewAgent(
            parser=RuleBasedCodeReviewRequestParser(),
            scanner=StaticScanner(CodeReviewReport((), (), ("notes.txt",))),
        ).review_paths(("notes.txt",))

        self.assertIn("Durum: İNCELEME YAPILMADI", response)
        self.assertNotIn("sorun bulunmadı", response)


class Architect:
    def plan(self, request):
        del request
        return ArchitecturePlan(
            summary="VALUE değerini güncelle.",
            existing_files=("a.py",),
            new_files=(),
            steps=(ArchitectureStep("Güncelle", "VALUE değerini değiştir.", ("a.py",)),),
            risks=(),
            tests=(),
            notes=(),
        )


class ProposalPreparer:
    def prepare_project_edit(self, request):
        del request
        return ProjectEditProposal(
            instruction="VALUE değerini 2 yap",
            edits=(
                EditProposal(
                    path="a.py",
                    updated_content="VALUE = 2\n",
                    expected_sha256="hash",
                    diff="-VALUE = 1\n+VALUE = 2",
                    original_character_count=10,
                    updated_character_count=10,
                ),
            ),
        )


class ProposalApplier:
    def apply_project_edit(self, proposal):
        del proposal
        return ProjectEditOutcome((EditOutcome("a.py", 10, 10),))


class Reviewer:
    def __init__(self):
        self.calls = []

    def review_paths(self, paths):
        self.calls.append(paths)
        return "CODE REVIEW RAPORU\nDurum: UYGUN"


class CodingReviewIntegrationTests(unittest.TestCase):
    def test_runs_code_review_after_approved_change(self):
        reviewer = Reviewer()
        coordinator = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(),
            architect=Architect(),
            proposal_preparer=ProposalPreparer(),
            proposal_applier=ProposalApplier(),
            code_reviewer=reviewer,
        )
        coordinator.resolve("kodla: a.py içinde VALUE değerini 2 yap")

        response = coordinator.resolve("kod değişikliğini onayla")

        self.assertEqual(reviewer.calls, [("a.py",)])
        self.assertIn("CODE REVIEW RAPORU", response or "")


if __name__ == "__main__":
    unittest.main()
