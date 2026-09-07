import re
from dataclasses import dataclass
from pathlib import Path

from boru.persistence import AtomicJsonFileStore, JsonFileReadError, JsonFileWriteError
from boru.tasks.models import TaskItem, TaskPlan, TaskStatus


@dataclass(frozen=True, slots=True)
class TaskJournalEntry:
    sequence: int
    event: str
    task_id: str = ""
    status: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("Task günlük sırası pozitif olmalıdır.")
        event = self.event.strip()
        task_id = self.task_id.strip().upper()
        status = self.status.strip()
        note = self.note.strip()
        if event not in {"plan_created", "task_status", "task_recovered"}:
            raise ValueError("Task günlük olayı geçersiz.")
        if task_id and re.fullmatch(r"TASK-[1-9]\d*", task_id) is None:
            raise ValueError("Task günlük kimliği geçersiz.")
        if status and status not in {item.value for item in TaskStatus}:
            raise ValueError("Task günlük durumu geçersiz.")
        if len(note) > 2000:
            raise ValueError("Task günlük notu çok uzun.")
        object.__setattr__(self, "event", event)
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "note", note)


@dataclass(frozen=True, slots=True)
class TaskCheckpoint:
    plan: TaskPlan | None
    journal: tuple[TaskJournalEntry, ...] = ()


class JsonTaskCheckpointRepository:
    """Persist one bounded task plan and journal through atomic JSON replacement."""

    _VERSION = 1
    _MAX_BYTES = 256 * 1024
    _MAX_JOURNAL = 100
    _SECRET_PATTERNS = (
        re.compile(r"\bsk-(?:live-|proj-)?[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )

    def __init__(self, file_path: str | Path) -> None:
        self._store = AtomicJsonFileStore(file_path)

    @property
    def path(self) -> Path:
        return self._store.path

    def load(self) -> TaskCheckpoint:
        try:
            if self.path.exists() and self.path.stat().st_size > self._MAX_BYTES:
                raise RuntimeError("Task checkpoint dosyası boyut sınırını aşıyor.")
            data = self._store.read()
        except (JsonFileReadError, OSError) as error:
            raise RuntimeError(f"Task checkpoint okunamadı: {self.path}") from error
        if data is None:
            return TaskCheckpoint(None)
        try:
            return self._decode(data)
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Task checkpoint geçerli bir V1 belgesi değil.") from error

    def save(self, checkpoint: TaskCheckpoint) -> None:
        self._validate_safe(checkpoint)
        try:
            self._store.write(self._encode(checkpoint))
        except JsonFileWriteError as error:
            raise RuntimeError(f"Task checkpoint yazılamadı: {self.path}") from error

    def _decode(self, data: object) -> TaskCheckpoint:
        if not isinstance(data, dict) or data.get("version") != self._VERSION:
            raise ValueError("Checkpoint sürümü geçersiz.")
        raw_plan = data.get("plan")
        raw_journal = data.get("journal")
        if raw_plan is not None and not isinstance(raw_plan, dict):
            raise TypeError("Plan nesne olmalıdır.")
        if not isinstance(raw_journal, list) or len(raw_journal) > self._MAX_JOURNAL:
            raise ValueError("Task günlüğü geçersiz veya sınırı aşıyor.")
        plan = self._decode_plan(raw_plan) if raw_plan is not None else None
        journal = tuple(self._decode_entry(item) for item in raw_journal)
        checkpoint = TaskCheckpoint(plan, journal)
        self._validate_safe(checkpoint)
        return checkpoint

    @staticmethod
    def _decode_plan(data: dict[str, object]) -> TaskPlan:
        raw_tasks = data["tasks"]
        if not isinstance(raw_tasks, list) or not 1 <= len(raw_tasks) <= 12:
            raise ValueError("Checkpoint task sayısı geçersiz.")
        tasks = []
        for raw in raw_tasks:
            if not isinstance(raw, dict):
                raise TypeError("Checkpoint task kaydı nesne olmalıdır.")
            tasks.append(
                TaskItem(
                    task_id=JsonTaskCheckpointRepository._required_string(raw, "task_id"),
                    title=JsonTaskCheckpointRepository._required_string(raw, "title"),
                    description=JsonTaskCheckpointRepository._required_string(raw, "description"),
                    files=JsonTaskCheckpointRepository._string_tuple(raw["files"]),
                    dependencies=JsonTaskCheckpointRepository._string_tuple(raw["dependencies"]),
                    status=TaskStatus(JsonTaskCheckpointRepository._required_string(raw, "status")),
                    note=JsonTaskCheckpointRepository._required_string(raw, "note"),
                )
            )
        return TaskPlan(
            JsonTaskCheckpointRepository._required_string(data, "objective"),
            JsonTaskCheckpointRepository._required_string(data, "summary"),
            tuple(tasks),
        )

    @staticmethod
    def _decode_entry(data: object) -> TaskJournalEntry:
        if not isinstance(data, dict):
            raise TypeError("Task günlük kaydı nesne olmalıdır.")
        return TaskJournalEntry(
            sequence=data["sequence"],
            event=JsonTaskCheckpointRepository._required_string(data, "event"),
            task_id=JsonTaskCheckpointRepository._optional_string(data, "task_id"),
            status=JsonTaskCheckpointRepository._optional_string(data, "status"),
            note=JsonTaskCheckpointRepository._optional_string(data, "note"),
        )

    @staticmethod
    def _required_string(data: dict[str, object], key: str) -> str:
        value = data[key]
        if not isinstance(value, str):
            raise TypeError(f"Checkpoint {key} alanı metin olmalıdır.")
        return value

    @staticmethod
    def _optional_string(data: dict[str, object], key: str) -> str:
        value = data.get(key, "")
        if not isinstance(value, str):
            raise TypeError(f"Checkpoint {key} alanı metin olmalıdır.")
        return value

    @staticmethod
    def _string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise TypeError("Checkpoint liste alanı metinlerden oluşmalıdır.")
        return tuple(value)

    @classmethod
    def _encode(cls, checkpoint: TaskCheckpoint) -> dict[str, object]:
        return {
            "version": cls._VERSION,
            "plan": cls._encode_plan(checkpoint.plan) if checkpoint.plan is not None else None,
            "journal": [
                {
                    "sequence": item.sequence,
                    "event": item.event,
                    "task_id": item.task_id,
                    "status": item.status,
                    "note": item.note,
                }
                for item in checkpoint.journal
            ],
        }

    @staticmethod
    def _encode_plan(plan: TaskPlan) -> dict[str, object]:
        return {
            "objective": plan.objective,
            "summary": plan.summary,
            "tasks": [
                {
                    "task_id": item.task_id,
                    "title": item.title,
                    "description": item.description,
                    "files": list(item.files),
                    "dependencies": list(item.dependencies),
                    "status": item.status.value,
                    "note": item.note,
                }
                for item in plan.tasks
            ],
        }

    @classmethod
    def _validate_safe(cls, checkpoint: TaskCheckpoint) -> None:
        cls._validate_journal(checkpoint.journal)
        if checkpoint.plan is None:
            return
        values = cls._validated_plan_values(checkpoint.plan)
        combined = "\n".join(values)
        if any(pattern.search(combined) for pattern in cls._SECRET_PATTERNS):
            raise ValueError("Hassas değer içeren task planı kalıcı checkpoint'e yazılamaz.")

    @classmethod
    def _validate_journal(cls, journal: tuple[TaskJournalEntry, ...]) -> None:
        if len(journal) > cls._MAX_JOURNAL:
            raise ValueError("Task günlüğü en fazla 100 kayıt içerebilir.")
        sequences = tuple(item.sequence for item in journal)
        if sequences != tuple(sorted(set(sequences))):
            raise ValueError("Task günlük sırası artan ve benzersiz olmalıdır.")

    @staticmethod
    def _validated_plan_values(plan: TaskPlan) -> list[str]:
        if len(plan.objective) > 4000 or len(plan.summary) > 4000 or len(plan.tasks) > 12:
            raise ValueError("Task checkpoint plan sınırlarını aşıyor.")
        values = [plan.objective, plan.summary]
        for item in plan.tasks:
            if len(item.title) > 500 or len(item.description) > 8000 or len(item.note) > 2000:
                raise ValueError("Task checkpoint metin sınırlarını aşıyor.")
            values.extend((item.title, item.description, item.note))
        return values
