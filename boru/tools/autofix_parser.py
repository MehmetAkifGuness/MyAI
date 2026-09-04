import re

from boru.tools.command_contracts import CommandRequestParser
from boru.tools.command_models import CommandKind, CommandRequest


class RuleBasedAutoFixRequestParser:
    _REQUEST = re.compile(
        r"^\s*(?:otomatik\s+düzelt|hata\s+düzelt)\s*:\s*(?P<command>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _INTENT = re.compile(
        r"^\s*(?:otomatik\s+düzelt|hata\s+düzelt)\b",
        re.IGNORECASE,
    )
    _SUPPORTED = {
        CommandKind.UNITTEST,
        CommandKind.PYTEST,
        CommandKind.RUFF,
        CommandKind.MYPY,
    }

    def __init__(self, command_parser: CommandRequestParser) -> None:
        self._command_parser = command_parser

    def parse(self, user_message: str) -> CommandRequest | None:
        match = self._REQUEST.fullmatch(user_message)
        if match is None:
            return None

        command_text = match.group("command")
        request = self._command_parser.parse(command_text)
        if request is None or request.kind not in self._SUPPORTED:
            raise ValueError("Yalnızca desteklenen test ve analiz komutları kullanılabilir.")
        return request

    def is_command_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None
