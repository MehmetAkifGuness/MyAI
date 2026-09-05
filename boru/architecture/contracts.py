from typing import Protocol

from boru.architecture.models import ArchitecturePlan, ArchitectureRequest


class ArchitectureRequestParser(Protocol):
    def parse(self, user_message: str) -> ArchitectureRequest | None:
        ...

    def is_architecture_intent(self, user_message: str) -> bool:
        ...


class ArchitecturePlanner(Protocol):
    def plan(self, request: ArchitectureRequest) -> ArchitecturePlan:
        ...
