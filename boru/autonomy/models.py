from dataclasses import dataclass
from enum import Enum


class AutonomyAction(str, Enum):
    DEVELOP = "develop"
    PLAN = "plan"
    START = "start"
    CONTINUE = "continue"
    STATUS = "status"
    PAUSE = "pause"
    RETRY = "retry"
    VERIFY = "verify"
    SUMMARY = "summary"
    ARCHIVE = "archive"
    LIMITS = "limits"
    HELP = "help"
    DIAGNOSE = "diagnose"
    REPAIR = "repair"
    HEALTH = "health"


@dataclass(frozen=True, slots=True)
class AutonomyCommand:
    action: AutonomyAction
    value: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", self.value.strip())
