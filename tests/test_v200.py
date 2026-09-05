import tempfile
import unittest
from pathlib import Path

from boru.architecture import ArchitecturePlan, ArchitectureStep
from boru.coding import ControlledCodingCoordinator, RuleBasedCodingRequestParser
from boru.memory import ConservativeMemoryDecisionGate
from boru.security import (
    PythonSecurityScanner,
    RuleBasedSecurityRequestParser,
    SecurityAgent,
    SecurityFinding,
    SecurityScanReport,
    SecuritySeverity,
)
from boru.tools import EditOutcome, EditProposal, ProjectEditOutcome, ProjectEditProposal


class SecurityParserTests(unittest.TestCase):
    def test_parses_scoped_security_request(self):
        request = RuleBasedSecurityRequestParser().parse(
            "güvenlik tara: boru/service.py, boru/api.py"
        )

        self.assertEqual(request.paths, ("boru/service.py", "boru/api.py"))

    def test_rejects_duplicate_paths(self):
        with self.assertRaisesRegex(ValueError, "birden fazla"):
            RuleBasedSecurityRequestParser().parse("security: a.py, A.py")

    def test_security_request_is_not_memory_candidate(self):
        self.assertFalse(
            ConservativeMemoryDecisionGate().should_evaluate(
                "güvenlik tara: boru/service.py"
            )
        )


class PythonSecurityScannerTests(unittest.TestCase):
    def test_detects_high_risk_python_patterns_and_import_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unsafe.py"
            target.write_text(
                "import os\n"
                "import pickle\n"
                "import requests as http\n"
                "import subprocess as sp\n"
                "import tempfile\n"
                "import yaml\n\n"
                "API_KEY = 'sk-live-123456789'\n"
                "query = f'SELECT * FROM users WHERE id={user_id}'\n"
                "eval(user_input)\n"
                "os.system(user_input)\n"
                "sp.run(user_input, shell=True)\n"
                "pickle.loads(payload)\n"
                "yaml.load(payload)\n"
                "cursor.execute(query)\n"
                "http.get(url, verify=False)\n"
                "os.chmod(path, 0o777)\n"
                "tempfile.mktemp()\n"
                "open('../secret.txt')\n"
                "print(API_KEY)\n",
                encoding="utf-8",
            )

            report = PythonSecurityScanner(directory).scan(("unsafe.py",))

            rules = {finding.rule for finding in report.findings}
            self.assertEqual(
                rules,
                {
                    "PY-COMMAND-INJECTION",
                    "PY-SUBPROCESS-SHELL",
                    "PY-EVAL-EXEC",
                    "PY-HARDCODED-SECRET",
                    "PY-INSECURE-DESERIALIZATION",
                    "PY-INSECURE-TEMPFILE",
                    "PY-PATH-TRAVERSAL",
                    "PY-SECRET-LEAKAGE",
                    "PY-SQL-INJECTION",
                    "PY-TLS-VERIFY-DISABLED",
                    "PY-UNSAFE-YAML",
                    "PY-WORLD-WRITABLE",
                },
            )
            self.assertEqual(report.scanned_paths, ("unsafe.py",))

    def test_safe_equivalents_have_no_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "safe.py"
            target.write_text(
                "import ast\n"
                "import json\n"
                "import os\n"
                "import requests\n"
                "import subprocess\n"
                "import tempfile\n"
                "import yaml\n\n"
                "API_KEY = os.getenv('API_KEY')\n"
                "ast.literal_eval(value)\n"
                "subprocess.run(['python', '-V'], shell=False)\n"
                "json.loads(payload)\n"
                "yaml.safe_load(payload)\n"
                "cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))\n"
                "requests.get(url)\n"
                "os.chmod(path, 0o600)\n"
                "tempfile.NamedTemporaryFile()\n",
                encoding="utf-8",
            )

            report = PythonSecurityScanner(directory).scan(("safe.py",))

            self.assertEqual(report.findings, ())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "Workspace dışına"):
                PythonSecurityScanner(directory).scan(("../outside.py",))

    def test_reports_non_python_file_as_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "notes.txt"
            target.write_text("eval(user_input)", encoding="utf-8")

            report = PythonSecurityScanner(directory).scan(("notes.txt",))

            self.assertEqual(report.scanned_paths, ())
            self.assertEqual(report.skipped_paths, ("notes.txt",))

    def test_flags_unvalidated_archive_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "archive.py"
            target.write_text("archive.extractall(target)\n", encoding="utf-8")

            report = PythonSecurityScanner(directory).scan(("archive.py",))

            self.assertEqual(report.findings[0].rule, "PY-ARCHIVE-TRAVERSAL")


class StaticScanner:
    def __init__(self, findings=()):
        self.findings = findings
        self.calls = []

    def scan(self, paths):
        self.calls.append(paths)
        return SecurityScanReport(paths, self.findings)


class SecurityCoordinatorTests(unittest.TestCase):
    def test_reports_clean_scan_and_scope_limit(self):
        scanner = StaticScanner()
        agent = SecurityAgent(
            parser=RuleBasedSecurityRequestParser(),
            scanner=scanner,
        )

        response = agent.resolve("security agent: a.py")

        self.assertIn("Durum: TEMİZ", response or "")
        self.assertIn("Kapsam notu:", response or "")
        self.assertEqual(scanner.calls, [("a.py",)])

    def test_does_not_report_unsupported_file_as_clean(self):
        class SkippedScanner:
            def scan(self, paths):
                return SecurityScanReport((), (), paths)

        response = SecurityAgent(
            parser=RuleBasedSecurityRequestParser(),
            scanner=SkippedScanner(),
        ).review_paths(("notes.txt",))

        self.assertIn("Durum: TARAMA YAPILMADI", response)
        self.assertNotIn("risk bulunmadı", response)

    def test_orders_and_summarizes_findings_by_severity(self):
        findings = (
            SecurityFinding(
                "a.py",
                2,
                "LOW-RULE",
                SecuritySeverity.LOW,
                "Düşük risk",
                "Düzelt",
            ),
            SecurityFinding(
                "a.py",
                1,
                "CRITICAL-RULE",
                SecuritySeverity.CRITICAL,
                "Kritik risk",
                "Hemen düzelt",
            ),
        )
        response = SecurityAgent(
            parser=RuleBasedSecurityRequestParser(),
            scanner=StaticScanner(findings),
        ).review_paths(("a.py",))

        self.assertIn("Durum: RİSK BULUNDU", response)
        self.assertIn("CRITICAL=1, LOW=1", response)


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


class RegressionRunner:
    def run_for_paths(self, paths):
        return f"TEST AGENT RAPORU\nDosya: {paths[0]}"


class SecurityReviewer:
    def __init__(self):
        self.calls = []

    def review_paths(self, paths):
        self.calls.append(paths)
        return f"SECURITY AGENT RAPORU\nDosya: {paths[0]}"


class CodingSecurityIntegrationTests(unittest.TestCase):
    def test_runs_security_after_regression_on_approved_change(self):
        reviewer = SecurityReviewer()
        coordinator = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(),
            architect=Architect(),
            proposal_preparer=ProposalPreparer(),
            proposal_applier=ProposalApplier(),
            regression_runner=RegressionRunner(),
            security_reviewer=reviewer,
        )
        coordinator.resolve("kodla: a.py içinde VALUE değerini 2 yap")

        response = coordinator.resolve("kod değişikliğini onayla")

        self.assertEqual(reviewer.calls, [("a.py",)])
        self.assertLess(
            (response or "").index("TEST AGENT RAPORU"),
            (response or "").index("SECURITY AGENT RAPORU"),
        )


if __name__ == "__main__":
    unittest.main()
