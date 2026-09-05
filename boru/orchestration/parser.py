import re

from boru.orchestration.models import OrchestrationRequest


class RuleBasedOrchestrationRequestParser:
    _PATTERN = re.compile(
        r"^\s*(?:ajan\s+görevi|ajan\s+akışı|görev\s+başlat|orchestrate)\s*:\s*"
        r"(?P<task>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _INTENT = re.compile(
        r"^\s*(?:ajan\s+görevi|ajan\s+akışı|görev\s+başlat|orchestrate)\b",
        re.IGNORECASE,
    )

    def __init__(self, max_task_characters: int = 4000) -> None:
        if max_task_characters < 1:
            raise ValueError("Orchestrator görev sınırı pozitif olmalıdır.")
        self._max_task_characters = max_task_characters

    def parse(self, user_message: str) -> OrchestrationRequest | None:
        match = self._PATTERN.fullmatch(user_message)
        if match is None:
            return None
        task = match.group("task").strip()
        if len(task) > self._max_task_characters:
            raise ValueError(
                f"Ajan görevi en fazla {self._max_task_characters} karakter olabilir."
            )
        return OrchestrationRequest(task)

    def is_orchestration_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None

