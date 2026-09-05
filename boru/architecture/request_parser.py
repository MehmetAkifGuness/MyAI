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
    _EXPLICIT_SCOPE = re.compile(
        r"\b(?:yalnızca|sadece)\b.*\bdosya\w*\b",
        re.IGNORECASE | re.DOTALL,
    )
    _FILE_PATH = re.compile(
        r"(?<![\w.-])(?:[\w.-]+[/\\])*[\w.-]+\.[A-Za-z0-9]+",
        re.UNICODE,
    )

    def parse(self, user_message: str) -> ArchitectureRequest | None:
        match = self._REQUEST.fullmatch(user_message)
        if match is None:
            return None
        return self.parse_task(match.group("task"))

    def parse_task(self, task: str) -> ArchitectureRequest:
        file_scope = ()
        if self._EXPLICIT_SCOPE.search(task) is not None:
            file_scope = tuple(
                path.replace("\\", "/")
                for path in self._FILE_PATH.findall(task)
            )
        return ArchitectureRequest(task, file_scope)

    def is_architecture_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None
