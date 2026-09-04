from boru.tools.command_contracts import (
    CommandExecutor,
    CommandPolicy,
    CommandRequestParser,
    TestResultParser,
)
from boru.tools.command_models import (
    CommandExecutionResult,
    CommandRisk,
    TestSummary,
)


class SafeCommandCoordinator:
    _USAGE = (
        "Serbest sistem komutları çalıştırılmaz. Desteklenen biçimler: "
        "'testleri çalıştır', 'unittest çalıştır: hedef', "
        "'pytest çalıştır: hedef', 'ruff çalıştır: hedef' veya "
        "'mypy çalıştır: hedef'."
    )

    def __init__(
        self,
        parser: CommandRequestParser,
        policy: CommandPolicy,
        executor: CommandExecutor,
        result_parser: TestResultParser,
    ) -> None:
        self._parser = parser
        self._policy = policy
        self._executor = executor
        self._result_parser = result_parser

    def resolve(self, user_message: str) -> str | None:
        try:
            request = self._parser.parse(user_message)
        except ValueError as error:
            return f"Komut isteği reddedildi: {error} {self._USAGE}"

        if request is None:
            if self._parser.is_command_intent(user_message):
                return self._USAGE
            return None

        try:
            command = self._policy.build(request)
            if command.risk is not CommandRisk.SAFE:
                return "Bu komut güvenlik politikası tarafından engellendi."
            result = self._executor.execute(command)
        except (OSError, PermissionError, ValueError) as error:
            return f"Komut çalıştırılamadı: {error}"

        return self._format_result(result, self._result_parser.parse(result))

    @staticmethod
    def _format_result(
        result: CommandExecutionResult,
        summary: TestSummary | None,
    ) -> str:
        if result.timed_out:
            status = "ZAMAN AŞIMI"
        elif result.output_limit_exceeded:
            status = "ÇIKTI LİMİTİ AŞILDI"
        elif result.succeeded:
            status = "BAŞARILI"
        else:
            status = "BAŞARISIZ"

        lines = [
            f"Komut: {result.command.display}",
            f"Durum: {status}",
            f"Süre: {result.duration_seconds:.2f} saniye",
        ]
        if summary is not None:
            lines.append(SafeCommandCoordinator._format_summary(summary))
        if result.exit_code is not None:
            lines.append(f"Çıkış kodu: {result.exit_code}")
        if result.truncated:
            lines.append("Not: Çıktı güvenlik limiti nedeniyle kısaltıldı.")
        lines.extend(("Çıktı:", result.output.strip() or "(çıktı yok)"))
        return "\n".join(lines)

    @staticmethod
    def _format_summary(summary: TestSummary) -> str:
        if summary.total is None or summary.passed is None or summary.failed is None:
            return f"Test özeti ({summary.framework}): ayrıntılı sayılar belirlenemedi"

        text = (
            f"Testler ({summary.framework}): {summary.passed}/{summary.total} geçti, "
            f"{summary.failed} başarısız"
        )
        if summary.skipped:
            text += f", {summary.skipped} atlandı"
        return text
