from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from boru.tools.models import ToolResult


class AgentActionKind(str, Enum):
    TOOL = "tool"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class AgentAction:
    kind: AgentActionKind
    tool_name: str = ""
    arguments: Mapping[str, object] = field(default_factory=dict)
    answer: str = ""
    evidence: tuple[int, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", self.tool_name.strip())
        object.__setattr__(self, "answer", self.answer.strip())
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        if self.kind is AgentActionKind.TOOL:
            if not self.tool_name:
                raise ValueError("Tool eylemi tool_name gerektirir.")
            if self.answer or self.evidence:
                raise ValueError("Tool eylemi final yanıt veya kanıt içeremez.")
        elif self.tool_name or self.arguments:
            raise ValueError("Final eylemi tool çağrısı içeremez.")
        elif not self.answer:
            raise ValueError("Final eylemi boş yanıt içeremez.")


@dataclass(frozen=True, slots=True)
class AgentObservation:
    step: int
    tool_name: str
    arguments: Mapping[str, object]
    result: ToolResult

    def __post_init__(self) -> None:
        if self.step < 1:
            raise ValueError("Ajan adımı pozitif olmalıdır.")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))

