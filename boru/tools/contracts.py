from collections.abc import Sequence
from typing import Protocol

from boru.tools.models import (
    ToolCall,
    ToolDecision,
    ToolDefinition,
    ToolResult,
    ToolRisk,
)
from boru.tools.workspace import (
    DirectoryListing,
)


class Tool(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    @property
    def risk(self) -> ToolRisk:
        ...

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        ...


class ToolPlanner(Protocol):
    def plan(
        self,
        user_message: str,
    ) -> ToolDecision:
        ...


class ToolRegistryPort(Protocol):
    def get(
        self,
        name: str,
    ) -> Tool | None:
        ...

    def definitions(
        self,
    ) -> Sequence[ToolDefinition]:
        ...


class ToolPolicy(Protocol):
    def is_allowed(
        self,
        tool: Tool,
    ) -> bool:
        ...


class ToolExecutorPort(Protocol):
    def execute(
        self,
        call: ToolCall,
    ) -> ToolResult:
        ...


class ToolResultSynthesizer(Protocol):
    def synthesize(
        self,
        *,
        user_message: str,
        instruction: str,
        tool_call: ToolCall,
        tool_result: ToolResult,
    ) -> str:
        ...


class WorkspaceReader(Protocol):
    def list_directory(
        self,
        relative_path: str = ".",
    ) -> DirectoryListing:
        ...

    def read_text_file(
        self,
        relative_path: str,
    ) -> str:
        ...