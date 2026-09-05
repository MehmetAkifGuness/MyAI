from collections import Counter

from boru.reviewing.contracts import CodeReviewScanner
from boru.reviewing.parser import RuleBasedCodeReviewRequestParser
from boru.tools.workspace import WorkspaceAccessError


class CodeReviewAgent:
    _USAGE = (
        "Code Review Agent biçimi: "
        "'kod incele: kaynak/dosya.py[, ikinci/dosya.py]'."
    )

    def __init__(
        self,
        *,
        parser: RuleBasedCodeReviewRequestParser,
        scanner: CodeReviewScanner,
        max_findings: int = 30,
    ) -> None:
        if max_findings < 1:
            raise ValueError("Code Review Agent bulgu sınırı pozitif olmalıdır.")
        self._parser = parser
        self._scanner = scanner
        self._max_findings = max_findings

    def resolve(self, user_message: str) -> str | None:
        try:
            request = self._parser.parse(user_message)
        except ValueError as error:
            return f"Code Review Agent isteği geçersiz: {error} {self._USAGE}"
        if request is None:
            return self._USAGE if self._parser.is_review_intent(user_message) else None
        return self.review_paths(request.paths)

    def review_paths(self, paths: tuple[str, ...]) -> str:
        try:
            report = self._scanner.scan(paths)
        except (OSError, ValueError, WorkspaceAccessError) as error:
            return f"CODE REVIEW RAPORU\nDurum: İNCELEME BAŞARISIZ\nHata: {error}"

        if report.findings:
            status = "İYİLEŞTİRME GEREKLİ"
        elif report.reviewed_paths:
            status = "UYGUN"
        else:
            status = "İNCELEME YAPILMADI"
        lines = [
            "CODE REVIEW RAPORU",
            f"İncelenen dosya: {len(report.reviewed_paths)}",
            f"Bulgu: {len(report.findings)}",
            f"Durum: {status}",
        ]
        if report.skipped_paths:
            lines.append(
                "Atlanan (Python değil): " + ", ".join(report.skipped_paths)
            )
        findings = report.findings[: self._max_findings]
        if findings:
            counts = Counter(finding.severity.name for finding in report.findings)
            lines.append(
                "Özet: "
                + ", ".join(
                    f"{severity}={counts[severity]}"
                    for severity in ("ERROR", "WARNING", "INFO")
                    if counts[severity]
                )
            )
            for finding in findings:
                lines.extend((
                    "",
                    f"- [{finding.severity.name}] {finding.rule} "
                    f"{finding.path}:{finding.line}",
                    f"  {finding.message}",
                    f"  Öneri: {finding.recommendation}",
                ))
            if len(report.findings) > len(findings):
                lines.append(
                    f"Not: {len(report.findings) - len(findings)} ek bulgu gösterilmedi."
                )
        elif report.reviewed_paths:
            lines.append("İncelenen statik code review kurallarında sorun bulunmadı.")
        lines.append(
            "Kapsam notu: Göreve uygunluk, public API geriye uyumluluğu ve çalışma "
            "zamanı davranışı diff, test ve insan değerlendirmesi gerektirebilir."
        )
        return "\n".join(lines)

