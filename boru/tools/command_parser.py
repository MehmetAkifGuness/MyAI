import re

from boru.tools.command_models import CommandKind, CommandRequest


class RuleBasedCommandRequestParser:
    """Yalnızca desteklenen test ve statik analiz isteklerini ayrıştırır."""

    _TARGET = r"(?P<target>[A-Za-z0-9_./\\-]+)"
    _PATTERNS = (
        (
            CommandKind.UNITTEST,
            re.compile(r"^\s*(?:tüm\s+)?testleri\s+çalıştır\s*[.!]?\s*$", re.IGNORECASE),
        ),
        (
            CommandKind.UNITTEST,
            re.compile(r"^\s*unittest\s+çalıştır(?:\s*:\s*" + _TARGET + r")?\s*[.!]?\s*$", re.IGNORECASE),
        ),
        (
            CommandKind.PYTEST,
            re.compile(r"^\s*pytest\s+çalıştır(?:\s*:\s*" + _TARGET + r")?\s*[.!]?\s*$", re.IGNORECASE),
        ),
        (
            CommandKind.RUFF,
            re.compile(r"^\s*ruff\s+(?:kontrolü\s+)?çalıştır(?:\s*:\s*" + _TARGET + r")?\s*[.!]?\s*$", re.IGNORECASE),
        ),
        (
            CommandKind.MYPY,
            re.compile(r"^\s*mypy\s+(?:kontrolü\s+)?çalıştır(?:\s*:\s*" + _TARGET + r")?\s*[.!]?\s*$", re.IGNORECASE),
        ),
    )
    _INTENT = re.compile(
        r"(?:\b(?:testleri|unittest|pytest|ruff|mypy)\b.*\bçalıştır\b|"
        r"\b(?:komut|terminal|powershell|cmd)\b.*\bçalıştır\b|"
        r"\b(?:python|bash|sh|curl|wget|pip|npm|flutter|dotnet|mvn|gradle|git|rm|del|format|shutdown)\b)",
        re.IGNORECASE | re.DOTALL,
    )

    def parse(self, user_message: str) -> CommandRequest | None:
        for kind, pattern in self._PATTERNS:
            match = pattern.fullmatch(user_message)
            if match is None:
                continue

            target = match.groupdict().get("target") or ""
            self._validate_target(target)
            return CommandRequest(kind=kind, target=target)

        return None

    def is_command_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None

    @staticmethod
    def _validate_target(target: str) -> None:
        if not target:
            return

        normalized = target.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized:
            raise ValueError("Komut hedefi göreli olmalıdır.")

        if ".." in normalized.split("/"):
            raise ValueError("Workspace dışına çıkan komut hedefi kullanılamaz.")
