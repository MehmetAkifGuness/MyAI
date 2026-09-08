import re

from boru.autonomy.models import AutonomyAction, AutonomyCommand


class RuleBasedAutonomyCommandParser:
    """Parse a bounded command vocabulary without correcting approval phrases."""

    _REQUIRED_LEVEL = {
        AutonomyAction.DEVELOP: 0,
        AutonomyAction.CONTINUE: 0,
        AutonomyAction.STATUS: 0,
        AutonomyAction.PAUSE: 4,
        AutonomyAction.PLAN: 2,
        AutonomyAction.START: 3,
        AutonomyAction.RETRY: 6,
        AutonomyAction.VERIFY: 7,
        AutonomyAction.SUMMARY: 8,
        AutonomyAction.ARCHIVE: 9,
        AutonomyAction.LIMITS: 9,
        AutonomyAction.HELP: 1,
        AutonomyAction.DIAGNOSE: 11,
        AutonomyAction.REPAIR: 12,
        AutonomyAction.HEALTH: 13,
    }
    _VALUE_COMMANDS = (
        (AutonomyAction.DEVELOP, ("geliştir", "gelistir", "geliştr", "gelistr")),
        (AutonomyAction.PLAN, ("planla", "planl")),
        (AutonomyAction.RETRY, ("yeniden dene", "tekrar dene")),
        (AutonomyAction.VERIFY, ("doğrula", "dogrula", "doğrla")),
        (AutonomyAction.DIAGNOSE, ("teşhis", "teshis")),
        (AutonomyAction.REPAIR, ("onar",)),
    )
    _PLAIN_COMMANDS = (
        (AutonomyAction.CONTINUE, ("devam et", "devam")),
        (AutonomyAction.STATUS, ("durum", "drum")),
        (AutonomyAction.PAUSE, ("duraklat", "beklet")),
        (AutonomyAction.START, ("başlat", "baslat", "planı başlat", "plani baslat")),
        (AutonomyAction.SUMMARY, ("özet", "ozet", "kontrol paneli")),
        (AutonomyAction.ARCHIVE, ("arşivle", "arsivle")),
        (AutonomyAction.LIMITS, ("sınırlar", "sinirlar")),
        (AutonomyAction.HELP, ("yardım", "yardim")),
        (AutonomyAction.HEALTH, ("sağlık", "saglik")),
    )

    def __init__(self, feature_level: int = 0) -> None:
        if type(feature_level) is not int or not 0 <= feature_level <= 13:
            raise ValueError("Otonomi özellik seviyesi 0-13 arasında olmalıdır.")
        self.feature_level = feature_level

    def parse(self, message: str) -> AutonomyCommand | None:
        stripped = message.strip()
        if not stripped.casefold().startswith("otonom"):
            return None
        body = stripped[6:].strip()
        folded = " ".join(body.casefold().split())
        return (
            self._parse_checkpoint_resume(folded)
            or self._parse_v5(body, folded)
            or self._parse_value_command(body, folded)
            or self._parse_plain_command(folded)
        )

    def _parse_checkpoint_resume(self, folded: str) -> AutonomyCommand | None:
        if self.feature_level >= 5 and folded.rstrip(".!?") in {"sürdür", "surdur"}:
            return AutonomyCommand(AutonomyAction.CONTINUE)
        return None

    def _parse_v5(self, body: str, folded: str) -> AutonomyCommand | None:
        if self.feature_level < 10:
            return None
        labels = ("çalıştır", "calistir", "denetimli geliştir", "denetimli gelistir")
        value = self._match_value(body, folded, labels)
        if value is not None:
            return AutonomyCommand(AutonomyAction.DEVELOP, value)
        if folded.rstrip(".!?") == "kontrol merkezi":
            return AutonomyCommand(AutonomyAction.SUMMARY)
        return None

    def _parse_value_command(self, body: str, folded: str) -> AutonomyCommand | None:
        for action, labels in self._VALUE_COMMANDS:
            value = self._match_value(body, folded, self._labels(labels))
            if value is not None and self._enabled(action):
                return AutonomyCommand(action, value)
        return None

    def _parse_plain_command(self, folded: str) -> AutonomyCommand | None:
        value = folded.rstrip(".!?")
        for action, labels in self._PLAIN_COMMANDS:
            if value in self._labels(labels) and self._enabled(action):
                return AutonomyCommand(action)
        return None

    @staticmethod
    def _match_value(body: str, folded: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            if re.fullmatch(re.escape(label) + r"\s*:\s*(.+)", folded, re.DOTALL):
                return body[body.find(":") + 1 :].strip()
        return None

    @staticmethod
    def is_intent(message: str) -> bool:
        return message.strip().casefold().startswith("otonom")

    def usage(self) -> str:
        commands = [
            "otonom geliştir: hedef",
            "otonom devam et",
            "otonom durum",
            "otonom iptal",
        ]
        if self.feature_level >= 2:
            commands.append("otonom planla: hedef")
        if self.feature_level >= 3:
            commands.append("otonom başlat")
        if self.feature_level >= 4:
            commands.append("otonom duraklat")
        if self.feature_level >= 6:
            commands.append("otonom yeniden dene: TASK-1")
        if self.feature_level >= 7:
            commands.append("otonom doğrula: dosya.py")
        if self.feature_level >= 8:
            commands.append("otonom özet")
        if self.feature_level >= 9:
            commands.extend(("otonom arşivle", "otonom sınırlar"))
        if self.feature_level >= 10:
            commands.append("otonom denetimli geliştir: hedef")
        if self.feature_level >= 11:
            commands.append("otonom teşhis: TASK-1")
        if self.feature_level >= 12:
            commands.append("otonom onar: TASK-1")
        if self.feature_level >= 13:
            commands.append("otonom sağlık")
        return "Biçimler: " + "; ".join(f"'{item}'" for item in commands) + "."

    def _labels(self, labels: tuple[str, ...]) -> tuple[str, ...]:
        return labels if self.feature_level >= 1 else labels[:1]

    def _enabled(self, action: AutonomyAction) -> bool:
        return self.feature_level >= self._REQUIRED_LEVEL[action]
