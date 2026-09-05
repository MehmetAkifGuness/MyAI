from collections import Counter

from boru.security.contracts import SecurityScanner
from boru.security.models import SecuritySeverity
from boru.security.parser import RuleBasedSecurityRequestParser
from boru.tools.workspace import WorkspaceAccessError


class SecurityAgent:
    _USAGE = (
        "Security Agent biçimi: "
        "'güvenlik tara: kaynak/dosya.py[, ikinci/dosya.py]'."
    )

    def __init__(
        self,
        *,
        parser: RuleBasedSecurityRequestParser,
        scanner: SecurityScanner,
        max_findings: int = 30,
    ) -> None:
        if max_findings < 1:
            raise ValueError("Security Agent bulgu sınırı pozitif olmalıdır.")
        self._parser = parser
        self._scanner = scanner
        self._max_findings = max_findings

    def resolve(self, user_message: str) -> str | None:
        try:
            request = self._parser.parse(user_message)
        except ValueError as error:
            return f"Security Agent isteği geçersiz: {error} {self._USAGE}"
        if request is None:
            return self._USAGE if self._parser.is_security_intent(user_message) else None
        return self.review_paths(request.paths)

    def review_paths(self, paths: tuple[str, ...]) -> str:
        try:
            report = self._scanner.scan(paths)
        except (OSError, ValueError, WorkspaceAccessError) as error:
            return f"SECURITY AGENT RAPORU\nDurum: TARAMA BAŞARISIZ\nHata: {error}"

        findings = report.findings[: self._max_findings]
        if report.findings:
            status = "RİSK BULUNDU"
        elif report.scanned_paths:
            status = "TEMİZ"
        else:
            status = "TARAMA YAPILMADI"
        lines = [
            "SECURITY AGENT RAPORU",
            f"Taranan dosya: {len(report.scanned_paths)}",
            f"Bulgu: {len(report.findings)}",
            f"Durum: {status}",
        ]
        if report.skipped_paths:
            lines.append(
                "Atlanan (Python değil): " + ", ".join(report.skipped_paths)
            )
        if findings:
            counts = Counter(finding.severity.name for finding in report.findings)
            lines.append(
                "Özet: "
                + ", ".join(
                    f"{severity}={counts[severity]}"
                    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
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
        elif report.scanned_paths:
            lines.append("İncelenen statik güvenlik kurallarında risk bulunmadı.")
        lines.append(
            "Kapsam notu: Dependency CVE, çalışan servis authentication/authorization "
            "ve ağ testi bu yerel statik taramaya dahil değildir."
        )
        return "\n".join(lines)
