from dataclasses import replace
from pathlib import Path

from boru.tasks.checkpoint import (
    JsonTaskCheckpointRepository,
    TaskCheckpoint,
    TaskJournalEntry,
)
from boru.tasks.models import TaskItem, TaskPlan, TaskStatus
from boru.tasks.state import InMemoryTaskPlanState


class PersistentTaskPlanState(InMemoryTaskPlanState):
    """Persist task transitions and safely recover interrupted running tasks."""

    _MAX_JOURNAL = 100

    def __init__(self, repository: JsonTaskCheckpointRepository) -> None:
        super().__init__()
        self._repository = repository
        checkpoint = repository.load()
        self._plan = checkpoint.plan
        self._journal = list(checkpoint.journal)
        self._recover_interrupted_tasks()

    @property
    def checkpoint_path(self) -> Path:
        return self._repository.path

    def get_journal(self) -> tuple[TaskJournalEntry, ...]:
        with self._lock:
            return tuple(self._journal)

    def replace_plan(self, plan: TaskPlan) -> None:
        with self._lock:
            previous_plan = self._plan
            previous_journal = self._journal
            self._plan = plan
            self._journal = [TaskJournalEntry(1, "plan_created", note=plan.summary)]
            try:
                self._save()
            except (OSError, RuntimeError, ValueError):
                self._plan = previous_plan
                self._journal = previous_journal
                raise

    def transition(
        self,
        task_id: str,
        status: TaskStatus,
        note: str = "",
    ) -> TaskItem:
        with self._lock:
            previous_plan = self._plan
            previous_journal = list(self._journal)
            updated = super().transition(task_id, status, note)
            self._append("task_status", updated.task_id, updated.status.value, updated.note)
            try:
                self._save()
            except (OSError, RuntimeError, ValueError):
                self._plan = previous_plan
                self._journal = previous_journal
                raise
            return updated

    def _recover_interrupted_tasks(self) -> None:
        if self._plan is None:
            return
        tasks = []
        recovered = []
        for item in self._plan.tasks:
            if item.status is TaskStatus.RUNNING:
                note = "Yeniden başlatma sonrası onay bekleyen öneri yeniden hazırlanmalıdır."
                item = replace(item, status=TaskStatus.PENDING, note=note)
                recovered.append(item)
            tasks.append(item)
        if not recovered:
            return
        self._plan = replace(self._plan, tasks=tuple(tasks))
        for item in recovered:
            self._append("task_recovered", item.task_id, item.status.value, item.note)
        self._save()

    def _append(self, event: str, task_id: str = "", status: str = "", note: str = "") -> None:
        sequence = self._journal[-1].sequence + 1 if self._journal else 1
        self._journal.append(TaskJournalEntry(sequence, event, task_id, status, note))
        self._journal = self._journal[-self._MAX_JOURNAL :]

    def _save(self) -> None:
        self._repository.save(TaskCheckpoint(self._plan, tuple(self._journal)))
