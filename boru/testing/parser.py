import re

from boru.testing.models import TestAgentRequest


class RuleBasedTestAgentRequestParser:
    _PATTERN = re.compile(
        r"^\s*(?:test\s+ajanı|test\s+agent|tester)\s*:\s*(?P<paths>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _INTENT = re.compile(
        r"^\s*(?:test\s+ajanı|test\s+agent|tester)\b",
        re.IGNORECASE,
    )

    def __init__(self, max_paths: int = 8) -> None:
        if max_paths < 1:
            raise ValueError("Test Agent dosya sınırı pozitif olmalıdır.")
        self._max_paths = max_paths

    def parse(self, user_message: str) -> TestAgentRequest | None:
        match = self._PATTERN.fullmatch(user_message)
        if match is None:
            return None

        paths = tuple(
            path.strip().strip("`\"'")
            for path in match.group("paths").split(",")
            if path.strip()
        )
        if len(paths) > self._max_paths:
            raise ValueError(f"En fazla {self._max_paths} kaynak dosya belirtilebilir.")
        return TestAgentRequest(paths)

    def is_test_agent_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None

