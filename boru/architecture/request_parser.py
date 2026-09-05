import re

from boru.architecture.models import ArchitectureRequest


class RuleBasedArchitectureRequestParser:
    _REQUEST = re.compile(
        r"^\s*(?:mimari\s+planla|mimari\s+analiz|architect)\s*:\s*(?P<task>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _INTENT = re.compile(
        r"^\s*(?:mimari\s+(?:planla|analiz)|architect)\b",
        re.IGNORECASE,
    )

    def parse(self, user_message: str) -> ArchitectureRequest | None:
        match = self._REQUEST.fullmatch(user_message)
        if match is None:
            return None
        return ArchitectureRequest(match.group("task"))

    def is_architecture_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None
