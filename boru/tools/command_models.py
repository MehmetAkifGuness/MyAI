from dataclasses import dataclass
from enum import Enum


class CommandKind(str, Enum):
    UNITTEST = "unittest"
    PYTEST = "pytest"
    RUFF = "ruff"
    MYPY = "mypy"


class CommandRisk(str, Enum):
    SAFE = "safe"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CommandRequest:
    kind: CommandKind
    target: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", self.target.strip())


@dataclass(frozen=True, slots=True)
class CommandSpec:
    kind: CommandKind
    executable: str
    arguments: tuple[str, ...]
    display: str
    risk: CommandRisk

    def __post_init__(self) -> None:
        if not self.executable.strip():
            raise ValueError("Komut executable alanı boş olamaz.")
        if not self.display.strip():
            raise ValueError("Komut görünümü boş olamaz.")


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    command: CommandSpec
    exit_code: int | None
    duration_seconds: float
    output: str
    timed_out: bool = False
    output_limit_exceeded: bool = False
    truncated: bool = False

    @property
    def succeeded(self) -> bool:
        return (
            self.exit_code == 0
            and not self.timed_out
            and not self.output_limit_exceeded
        )


@dataclass(frozen=True, slots=True)
class TestSummary:
    framework: str
    total: int | None
    passed: int | None
    failed: int | None
    skipped: int | None = None
