import re

from boru.tools.command_models import CommandKind, CommandRequest


class RuleBasedGitRequestParser:
    """Yalnızca açıkça desteklenen Git işlemlerini ayrıştırır."""

    _READ_PATTERNS = (
        (CommandKind.GIT_STATUS, re.compile(r"^\s*git\s+(?:status|durum)\s*$", re.IGNORECASE)),
        (CommandKind.GIT_DIFF, re.compile(r"^\s*git\s+(?:diff|fark)\s*$", re.IGNORECASE)),
        (CommandKind.GIT_BRANCH, re.compile(r"^\s*git\s+(?:branch|dalları)\s*$", re.IGNORECASE)),
        (CommandKind.GIT_LOG, re.compile(r"^\s*git\s+(?:log|geçmişi)\s*$", re.IGNORECASE)),
    )
    _PATH_PATTERNS = (
        (CommandKind.GIT_ADD, re.compile(r"^\s*git\s+(?:add|ekle)\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)),
        (CommandKind.GIT_RESTORE, re.compile(r"^\s*git\s+(?:restore|geri\s+al)\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)),
    )
    _COMMIT = re.compile(r"^\s*git\s+commit\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
    _INTENT = re.compile(r"^\s*git\b", re.IGNORECASE)
    _SAFE_PATH = re.compile(r"^[A-Za-z0-9_./\\-]+$")

    def parse(self, user_message: str) -> CommandRequest | None:
        for kind, pattern in self._READ_PATTERNS:
            if pattern.fullmatch(user_message):
                return CommandRequest(kind)

        for kind, pattern in self._PATH_PATTERNS:
            match = pattern.fullmatch(user_message)
            if match:
                value = match.group("value")
                self.validate_path(value)
                return CommandRequest(kind, value)

        commit_match = self._COMMIT.fullmatch(user_message)
        if commit_match:
            message = commit_match.group("value").strip()
            self.validate_commit_message(message)
            return CommandRequest(CommandKind.GIT_COMMIT, message)

        return None

    def is_command_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None

    @classmethod
    def validate_path(cls, value: str) -> None:
        normalized = value.replace("\\", "/")
        if (
            cls._SAFE_PATH.fullmatch(value) is None
            or normalized.startswith("/")
            or ":" in normalized
            or ".." in normalized.split("/")
            or normalized == "."
            or normalized == ".git"
            or normalized.startswith(".git/")
        ):
            raise ValueError("Git hedefi güvenli bir göreli dosya yolu olmalıdır.")

    @staticmethod
    def validate_commit_message(message: str) -> None:
        if not message or len(message) > 200:
            raise ValueError("Commit mesajı 1-200 karakter arasında olmalıdır.")
        if any(ord(character) < 32 for character in message):
            raise ValueError("Commit mesajı kontrol karakteri içeremez.")
