from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from boru.models import ChatMessage


class StructuredChatModel(Protocol):
    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        ...

    def generate_structured(
        self,
        messages: Sequence[ChatMessage],
        schema: Mapping[str, Any],
    ) -> str:
        ...


class AgentRunner(Protocol):
    def run(self, objective: str) -> str:
        ...
