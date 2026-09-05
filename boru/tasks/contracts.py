from typing import Protocol

from boru.tasks.models import TaskPlan


class TaskPlanner(Protocol):
    def plan(self, objective: str) -> TaskPlan:
        ...


class AgentWorkflow(Protocol):
    @property
    def has_pending(self) -> bool:
        ...

    def resolve(self, user_message: str) -> str | None:
        ...

