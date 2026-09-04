from typing import Protocol

from boru.tools.command_models import (
    CommandExecutionResult,
    CommandRequest,
    CommandSpec,
    TestSummary,
)


class CommandRequestParser(Protocol):
    def parse(self, user_message: str) -> CommandRequest | None:
        ...

    def is_command_intent(self, user_message: str) -> bool:
        ...


class CommandPolicy(Protocol):
    def build(self, request: CommandRequest) -> CommandSpec:
        ...


class CommandExecutor(Protocol):
    def execute(self, command: CommandSpec) -> CommandExecutionResult:
        ...


class TestResultParser(Protocol):
    def parse(self, result: CommandExecutionResult) -> TestSummary | None:
        ...

