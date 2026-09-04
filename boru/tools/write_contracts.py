from typing import Protocol

from boru.tools.write_models import (
    WriteOutcome,
    WriteRequest,
)


class WriteRequestParser(Protocol):
    def parse(
        self,
        user_message: str,
    ) -> WriteRequest | None:
        ...


class WriteIntentDetector(Protocol):
    def is_write_intent(
        self,
        user_message: str,
    ) -> bool:
        ...


class WorkspaceWriter(Protocol):
    def write_text_file(
        self,
        relative_path: str,
        content: str,
    ) -> WriteOutcome:
        ...