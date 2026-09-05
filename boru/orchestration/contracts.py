from typing import Protocol


class CodingWorkflow(Protocol):
    @property
    def has_pending(self) -> bool:
        ...

    def resolve(self, user_message: str) -> str | None:
        ...

