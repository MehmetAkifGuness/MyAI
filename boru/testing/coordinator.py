from boru.testing.contracts import RelatedTestDiscoverer
from boru.testing.parser import RuleBasedTestAgentRequestParser
from boru.tools.command_contracts import CommandExecutor, CommandPolicy, TestResultParser
from boru.tools.command_coordinator import SafeCommandCoordinator
from boru.tools.command_models import CommandKind, CommandRequest, CommandRisk
from boru.tools.workspace import WorkspaceAccessError


class SafeTestAgent:
    _USAGE = "Test Agent biçimi: 'test ajanı: kaynak/dosya.py[, ikinci/dosya.py]'."

    def __init__(
        self,
        *,
        parser: RuleBasedTestAgentRequestParser,
        discovery: RelatedTestDiscoverer,
        policy: CommandPolicy,
        executor: CommandExecutor,
        result_parser: TestResultParser,
        max_failure_output_characters: int = 4000,
    ) -> None:
        if max_failure_output_characters < 1:
            raise ValueError("Test Agent çıktı sınırı pozitif olmalıdır.")
        self._parser = parser
        self._discovery = discovery
        self._policy = policy
        self._executor = executor
        self._result_parser = result_parser
        self._max_failure_output_characters = max_failure_output_characters

    def resolve(self, user_message: str) -> str | None:
        try:
            request = self._parser.parse(user_message)
        except ValueError as error:
            return f"Test Agent isteği geçersiz: {error} {self._USAGE}"
        if request is None:
            return self._USAGE if self._parser.is_test_agent_intent(user_message) else None
        return self.run_for_paths(request.source_paths)

    def run_for_paths(self, source_paths: tuple[str, ...]) -> str:
        try:
            selection = self._discovery.discover(source_paths)
        except (OSError, ValueError, WorkspaceAccessError) as error:
            return f"TEST AGENT RAPORU\nDurum: KEŞİF BAŞARISIZ\nHata: {error}"

        lines = [
            "TEST AGENT RAPORU",
            f"Kaynak dosya: {len(selection.source_paths)}",
            f"İlişkili test: {len(selection.test_paths)}",
            "Strateji: Yol, modül ve kaynak sembolü eşleşen mevcut unittest dosyaları.",
        ]
        if not selection.test_paths:
            lines.extend((
                "Durum: TEST BULUNAMADI",
                "Öneri: Değiştirilen davranış için hedefli bir unittest ekleyin.",
            ))
            return "\n".join(lines)

        passed = 0
        failed = 0
        failure_details: list[str] = []
        for test_path in selection.test_paths:
            try:
                command = self._policy.build(
                    CommandRequest(CommandKind.UNITTEST, test_path)
                )
                if command.risk is not CommandRisk.SAFE:
                    raise PermissionError(
                        "Test komutu güvenlik politikası tarafından engellendi."
                    )
                result = self._executor.execute(command)
            except (OSError, PermissionError, ValueError) as error:
                failed += 1
                lines.append(f"- BAŞLATILAMADI {test_path}: {error}")
                continue

            summary = self._result_parser.parse(result)
            if result.succeeded:
                passed += 1
                detail = (
                    SafeCommandCoordinator._format_summary(summary)
                    if summary is not None
                    else "başarılı"
                )
                lines.append(
                    f"- GEÇTİ {test_path} "
                    f"({result.duration_seconds:.2f} sn, {detail})"
                )
            else:
                failed += 1
                lines.append(f"- BAŞARISIZ {test_path} ({result.duration_seconds:.2f} sn)")
                output = result.output.strip() or "(çıktı yok)"
                if len(output) > self._max_failure_output_characters:
                    output = (
                        output[: self._max_failure_output_characters]
                        + "\n... (kısaltıldı)"
                    )
                failure_details.append(f"[{test_path}]\n{output}")

        lines.insert(3, f"Durum: {'BAŞARILI' if failed == 0 else 'BAŞARISIZ'}")
        lines.insert(
            4,
            f"Sonuç: {passed}/{len(selection.test_paths)} test dosyası geçti",
        )
        if failure_details:
            lines.extend(("", "Hata çıktıları:", *failure_details))
        return "\n".join(lines)
