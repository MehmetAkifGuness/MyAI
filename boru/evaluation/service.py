import hashlib
from pathlib import Path

from boru.evaluation.models import Check, EvaluationReport, Verdict
from boru.reviewing import PythonCodeReviewScanner
from boru.security import PythonSecurityScanner
from boru.testing import RelatedTestDiscovery
from boru.tools.command_models import CommandKind, CommandRequest
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.test_results import TestOutputParser
from boru.tools.workspace import ReadOnlyWorkspace


class EvidenceEvaluator:
    def __init__(self, root: Path, executor, *, max_paths: int = 8):
        if not 1 <= max_paths <= 12:
            raise ValueError("Değerlendirme dosya sınırı 1–12 arasında olmalıdır.")
        self._reader = ReadOnlyWorkspace(root)
        self._discovery = RelatedTestDiscovery(root)
        self._security = PythonSecurityScanner(root)
        self._review = PythonCodeReviewScanner(root)
        self._executor = executor
        self._max_paths = max_paths
        self.latest: EvaluationReport | None = None

    def evaluate(self, paths: tuple[str, ...]) -> EvaluationReport:
        if not 1 <= len(paths) <= self._max_paths:
            raise ValueError(f"Değerlendirme 1–{self._max_paths} dosya gerektirir.")
        selection = self._discovery.discover(paths)
        # Fingerprint both changed sources and the tests used as evidence.
        evidence_paths = tuple(dict.fromkeys((*selection.source_paths, *selection.test_paths)))
        before = self.fingerprints(evidence_paths)
        checks = [self._tests(selection.test_paths)]
        checks.extend((self._scan(paths, security=True), self._scan(paths, security=False)))
        stable = before == self.fingerprints(evidence_paths)
        checks.append(Check("Kaynak bütünlüğü", Verdict.PASS if stable else Verdict.UNKNOWN,
                            "SHA-256 değişmedi." if stable else "Kaynak/test dosyası çalışırken değişti."))
        self.latest = EvaluationReport(paths, before, tuple(checks))
        return self.latest

    def validate_paths(self, paths: tuple[str, ...]) -> str:
        try:
            return self.evaluate(paths).workflow_report()
        except (OSError, ValueError, RuntimeError) as error:
            return f"ÖZ DEĞERLENDİRME RAPORU\nDurum: KANIT YETERSİZ\n{error}"

    def static_findings(self, paths: tuple[str, ...]) -> tuple[tuple, ...]:
        findings = []
        for name, scanner in (("Security", self._security), ("Code Review", self._review)):
            report = scanner.scan(paths)
            findings.extend(
                (name, item.path, item.rule, int(item.severity), item.message)
                for item in report.findings
            )
        return tuple(findings)

    def fingerprints(self, paths: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
        return tuple((path, hashlib.sha256(self._reader.read_text_file(path).encode("utf-8")).hexdigest())
                     for path in paths)

    def is_current(self, report: EvaluationReport) -> bool:
        try:
            return report.fingerprints == self.fingerprints(tuple(path for path, _ in report.fingerprints))
        except (OSError, RuntimeError, ValueError):
            return False

    def _tests(self, paths: tuple[str, ...]) -> Check:
        if not paths:
            return Check("Test", Verdict.UNKNOWN, "İlişkili test bulunamadı.")
        details = []
        verdicts = []
        for path in paths:
            verdict, detail = self._test_file(path)
            details.append(detail)
            verdicts.append(verdict)
        overall = Verdict.FAIL if Verdict.FAIL in verdicts else (
            Verdict.UNKNOWN if Verdict.UNKNOWN in verdicts else Verdict.PASS)
        return Check("Test", overall, "\n".join(details))

    def _test_file(self, path: str):
        try:
            spec = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, path))
            result = self._executor.execute(spec)
        except (OSError, ValueError, RuntimeError) as error:
            return Verdict.UNKNOWN, f"{path}: çalıştırılamadı ({error})"
        verdict = self._test_verdict(result)
        return verdict, f"{path}: {verdict.value}; " + result.output[-1200:].strip()

    @staticmethod
    def _test_verdict(result) -> Verdict:
        summary = TestOutputParser().parse(result)
        if result.succeeded and summary and summary.total and not summary.skipped and not summary.failed:
            return Verdict.PASS
        if result.exit_code in {None, 125, 126, 127} or result.timed_out:
            return Verdict.UNKNOWN
        if result.succeeded or (summary and summary.total == 0):
            return Verdict.UNKNOWN
        return Verdict.FAIL

    def _scan(self, paths: tuple[str, ...], *, security: bool) -> Check:
        name = "Security" if security else "Code Review"
        try:
            report = (self._security if security else self._review).scan(paths)
            if report.skipped_paths:
                return Check(name, Verdict.UNKNOWN, "Taranamayan dosya: " + ", ".join(report.skipped_paths))
            details = tuple(f"{item.path}:{item.line} {item.rule}: {item.message}" for item in report.findings)
            return Check(name, Verdict.FAIL if details else Verdict.PASS,
                         "\n".join(details[:20]) or "İncelenen statik kurallarda bulgu yok.")
        except (OSError, ValueError, RuntimeError) as error:
            return Check(name, Verdict.UNKNOWN, str(error))
