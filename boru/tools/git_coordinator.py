from dataclasses import dataclass

from boru.tools.command_contracts import CommandExecutor, CommandPolicy, CommandRequestParser
from boru.tools.command_models import CommandExecutionResult, CommandKind, CommandRisk, CommandSpec


@dataclass(frozen=True, slots=True)
class PendingGitOperation:
    command: CommandSpec
    confirmation: str


class ControlledGitCoordinator:
    _USAGE = (
        "Desteklenen Git biçimleri: 'git durum', 'git fark', 'git dalları', "
        "'git geçmişi', 'git ekle: dosya', 'git commit: mesaj' ve "
        "'git geri al: dosya'. Serbest Git argümanları çalıştırılmaz."
    )

    def __init__(
        self,
        parser: CommandRequestParser,
        policy: CommandPolicy,
        executor: CommandExecutor,
    ) -> None:
        self._parser = parser
        self._policy = policy
        self._executor = executor
        self._pending: PendingGitOperation | None = None

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    def resolve(self, user_message: str) -> str | None:
        if self._pending is not None:
            return self._resolve_pending(user_message)

        try:
            request = self._parser.parse(user_message)
        except ValueError as error:
            return f"Git isteği reddedildi: {error} {self._USAGE}"

        if request is None:
            return self._USAGE if self._parser.is_command_intent(user_message) else None

        try:
            command = self._policy.build(request)
        except ValueError as error:
            return f"Git isteği reddedildi: {error}"

        if command.risk is CommandRisk.SAFE:
            return self._execute(command)
        if command.risk is not CommandRisk.REQUIRES_APPROVAL:
            return "Git işlemi güvenlik politikası tarafından engellendi."

        confirmation = (
            "git geri almayı onayla"
            if command.kind is CommandKind.GIT_RESTORE
            else "git işlemini onayla"
        )
        self._pending = PendingGitOperation(command, confirmation)
        risk = "DESTRUCTIVE" if command.kind is CommandKind.GIT_RESTORE else "WRITE"
        return (
            "Git işlemi onay bekliyor.\n"
            f"Risk: {risk}\n"
            f"Komut: {command.display}\n"
            f"Onaylamak için tam olarak '{confirmation}' yazın; vazgeçmek için 'iptal' yazın."
        )

    def _resolve_pending(self, user_message: str) -> str:
        pending = self._pending
        normalized = " ".join(user_message.casefold().split())
        if normalized in {"iptal", "vazgeç"}:
            self._pending = None
            return "Git işlemi iptal edildi."
        if normalized != pending.confirmation:
            return (
                "Zaten onay bekleyen bir Git işlemi var. "
                f"Onaylamak için '{pending.confirmation}', vazgeçmek için 'iptal' yazın."
            )

        self._pending = None
        return self._execute(pending.command)

    def _execute(self, command: CommandSpec) -> str:
        try:
            result = self._executor.execute(command)
        except (OSError, PermissionError, ValueError) as error:
            return f"Git komutu çalıştırılamadı: {error}"
        return self._format_result(result)

    @staticmethod
    def _format_result(result: CommandExecutionResult) -> str:
        if result.timed_out:
            status = "ZAMAN AŞIMI"
        elif result.output_limit_exceeded:
            status = "ÇIKTI LİMİTİ AŞILDI"
        elif result.succeeded:
            status = "BAŞARILI"
        else:
            status = "BAŞARISIZ"
        return "\n".join(
            (
                f"Git komutu: {result.command.display}",
                f"Durum: {status}",
                f"Süre: {result.duration_seconds:.2f} saniye",
                f"Çıkış kodu: {result.exit_code}",
                "Çıktı:",
                result.output.strip() or "(çıktı yok)",
            )
        )
