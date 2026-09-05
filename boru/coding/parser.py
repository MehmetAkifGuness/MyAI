import re

from boru.architecture.request_parser import RuleBasedArchitectureRequestParser
from boru.coding.models import CodingRequest


class RuleBasedCodingRequestParser:
    _REQUEST = re.compile(
        r"^\s*(?:kodla|coding|kod\s+değişikliği\s+hazırla)\s*:\s*(?P<task>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _INTENT = re.compile(
        r"^\s*(?:kodla|coding|kod\s+değişikliği\s+hazırla)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        architecture_parser: RuleBasedArchitectureRequestParser | None = None,
    ) -> None:
        self._architecture_parser = architecture_parser or RuleBasedArchitectureRequestParser()

    def parse(self, user_message: str) -> CodingRequest | None:
        match = self._REQUEST.fullmatch(user_message)
        if match is None:
            return None
        return CodingRequest(
            self._architecture_parser.parse_task(match.group("task"))
        )

    def is_coding_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None
