from dataclasses import dataclass
from enum import Enum


class ProjectMemoryAction(str, Enum):
    SHOW = "show"
    SAVE = "save"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class ProjectMemoryRequest:
    action: ProjectMemoryAction
    key: str = ""
    value: str = ""
