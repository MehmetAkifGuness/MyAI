from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ToolRisk(str, Enum):
    SAFE = "safe"
    READ_ONLY = "read_only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXECUTION = "execution"
    NETWORK = "network"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    risk: ToolRisk


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool_name: str
    arguments: Mapping[str, object] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        cleaned_name = self.tool_name.strip()
        if not cleaned_name:
            raise ValueError("Tool adı boş olamaz.")

        object.__setattr__(
            self,
            "tool_name",
            cleaned_name,
        )
        object.__setattr__(
            self,
            "arguments",
            MappingProxyType(
                dict(self.arguments)
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    success: bool
    content: str = ""
    error: str | None = None

    def __post_init__(self) -> None:
        if self.success and self.error:
            raise ValueError(
                "Başarılı tool sonucu hata içeremez."
            )

        if not self.success and not self.error:
            raise ValueError(
                "Başarısız tool sonucu hata açıklaması içermelidir."
            )


@dataclass(frozen=True, slots=True)
class ToolDecision:
    should_use_tool: bool
    tool_call: ToolCall | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.should_use_tool and self.tool_call is None:
            raise ValueError(
                "Tool kullanılacaksa ToolCall gereklidir."
            )

        if not self.should_use_tool and self.tool_call is not None:
            raise ValueError(
                "Tool kullanılmayacaksa ToolCall olmamalıdır."
            )

    @classmethod
    def no_tool(
        cls,
        reason: str = "",
    ) -> "ToolDecision":
        return cls(
            should_use_tool=False,
            reason=reason,
        )

    @classmethod
    def use(
        cls,
        tool_call: ToolCall,
        reason: str = "",
    ) -> "ToolDecision":
        return cls(
            should_use_tool=True,
            tool_call=tool_call,
            reason=reason,
        )