from collections.abc import Sequence
from typing import Protocol

from boru.models import ChatMessage


class ChatModel(Protocol):
    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        ...


class ContextBuilder(Protocol):
    def build(
        self,
        history: Sequence[ChatMessage],
    ) -> list[ChatMessage]:
        ...


class MessageObserver(Protocol):
    def observe(
        self,
        user_message: str,
    ) -> None:
        ...


class DirectResponseResolver(Protocol):
    def resolve(
        self,
        user_message: str,
    ) -> str | None:
        ...


class AssistantContextProvider(Protocol):
    def build_context(
        self,
        user_message: str,
    ) -> str:
        ...


class AssistantPort(Protocol):
    def reply(
        self,
        user_message: str,
    ) -> str:
        ...

    def reset_conversation(
        self,
    ) -> None:
        ...