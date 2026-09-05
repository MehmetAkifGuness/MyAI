import re
from dataclasses import dataclass
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskAction(str, Enum):
    PLAN = "plan"
    STATUS = "status"
    RUN = "run"
    RESET = "reset"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class TaskCommand:
    action: TaskAction
    value: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", self.value.strip())


@dataclass(frozen=True, slots=True)
class TaskItem:
    task_id: str
    title: str
    description: str
    files: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.PENDING
    note: str = ""

    def __post_init__(self) -> None:
        task_id = self.task_id.strip().upper()
        if re.fullmatch(r"TASK-[1-9]\d*", task_id) is None:
            raise ValueError("Task kimliği TASK-N biçiminde olmalıdır.")
        title = self.title.strip()
        description = self.description.strip()
        if not title or not description:
            raise ValueError("Task başlığı ve açıklaması boş olamaz.")
        files = tuple(
            dict.fromkeys(
                path.strip().replace("\\", "/")
                for path in self.files
                if path.strip()
            )
        )
        dependencies = tuple(
            dict.fromkeys(
                item.strip().upper()
                for item in self.dependencies
                if item.strip()
            )
        )
        if task_id in dependencies:
            raise ValueError("Task kendisine bağımlı olamaz.")
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "files", files)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "note", self.note.strip())


@dataclass(frozen=True, slots=True)
class TaskPlan:
    objective: str
    summary: str
    tasks: tuple[TaskItem, ...]

    def __post_init__(self) -> None:
        objective = self.objective.strip()
        summary = self.summary.strip()
        if not objective or not summary or not self.tasks:
            raise ValueError("Task planı hedef, özet ve en az bir task içermelidir.")
        identifiers = tuple(item.task_id for item in self.tasks)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Task planı yinelenen kimlik içeremez.")
        known: set[str] = set()
        for item in self.tasks:
            unknown = set(item.dependencies) - known
            if unknown:
                raise ValueError(
                    f"{item.task_id} önceki task dışında bağımlılık içeriyor: "
                    + ", ".join(sorted(unknown))
                )
            known.add(item.task_id)
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "summary", summary)
