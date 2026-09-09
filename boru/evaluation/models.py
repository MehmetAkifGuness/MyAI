from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    PASS = "GEÇTİ"
    FAIL = "BAŞARISIZ"
    UNKNOWN = "KANIT YETERSİZ"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    verdict: Verdict
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    paths: tuple[str, ...]
    fingerprints: tuple[tuple[str, str], ...]
    checks: tuple[Check, ...]

    @property
    def verdict(self) -> Verdict:
        if any(check.verdict is Verdict.FAIL for check in self.checks):
            return Verdict.FAIL
        if not self.checks or any(check.verdict is Verdict.UNKNOWN for check in self.checks):
            return Verdict.UNKNOWN
        return Verdict.PASS

    def render(self) -> str:
        lines = ["ÖZ DEĞERLENDİRME RAPORU", f"Durum: {self.verdict.value}",
                 "Dosyalar: " + ", ".join(self.paths)]
        for check in self.checks:
            lines.append(f"- {check.name}: {check.verdict.value}\n  {check.detail}")
        lines.append(
            "Kapsam: testler ve statik kurallar; iş gereksinimlerinin tamamı, "
            "CVE ve çalışma zamanı yetkilendirmesi bu raporla doğrulanmış sayılmaz."
        )
        return "\n".join(lines)

    def workflow_report(self) -> str:
        headers = {"Test": ("TEST AGENT RAPORU", "BAŞARILI"),
                   "Security": ("SECURITY AGENT RAPORU", "TEMİZ"),
                   "Code Review": ("CODE REVIEW RAPORU", "UYGUN")}
        sections = []
        for name, (header, success) in headers.items():
            check = next((item for item in self.checks if item.name == name), None)
            if check is None or check.verdict is Verdict.FAIL:
                status = "BAŞARISIZ"
            elif check.verdict is Verdict.PASS:
                status = (
                    "YENİ BULGU YOK"
                    if check.detail.startswith("Yeni bulgu yok;")
                    else success
                )
            elif name == "Test" and "İlişkili test bulunamadı" in check.detail:
                status = "TEST BULUNAMADI"
            else:
                status = "KANIT YETERSİZ"
            if name == "Test" and any(c.name == "Kaynak bütünlüğü" and c.verdict is not Verdict.PASS for c in self.checks):
                status = "BAŞARISIZ"
            sections.append(f"{header}\nDurum: {status}")
        return "\n\n".join((*sections, self.render()))
