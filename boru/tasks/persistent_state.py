from dataclasses import replace
from pathlib import Path

from boru.tasks.checkpoint import (
    JsonTaskCheckpointRepository,
    TaskCheckpoint,
    TaskJournalEntry,
)
from boru.tasks.models import TaskItem, TaskPlan, TaskStatus
from boru.tasks.source_guard import (
    TaskSourceDriftError,
    TaskSourceFingerprint,
    TaskSourceFingerprintGuard,
)
from boru.tasks.state import InMemoryTaskPlanState


class PersistentTaskPlanState(InMemoryTaskPlanState):
    """Persist task transitions and safely recover interrupted running tasks."""

    _MAX_JOURNAL = 100

    def __init__(
        self,
        repository: JsonTaskCheckpointRepository,
        source_guard: TaskSourceFingerprintGuard | None = None,
    ) -> None:
        super().__init__()
        self._repository = repository
        self._source_guard = source_guard
        checkpoint = repository.load()
        self._plan = checkpoint.plan
        self._journal = list(checkpoint.journal)
        self._fingerprints = checkpoint.fingerprints
        self._recover_interrupted_tasks()

    @property
    def checkpoint_path(self) -> Path:
        return self._repository.path

    @property
    def checkpoint_schema(self) -> str:
        return self._repository.schema_label

    @property
    def checkpoint_migrated_from(self) -> int | None:
        return self._repository.last_migrated_from

    def get_journal(self) -> tuple[TaskJournalEntry, ...]:
        with self._lock:
            return tuple(self._journal)

    def replace_plan(self, plan: TaskPlan) -> None:
        with self._lock:
            fingerprints = self._snapshot_plan(plan)
            previous_plan = self._plan
            previous_journal = self._journal
            previous_fingerprints = self._fingerprints
            self._plan = plan
            self._journal = [TaskJournalEntry(1, "plan_created", note=plan.summary)]
            self._fingerprints = fingerprints
            try:
                self._save()
            except (OSError, RuntimeError, ValueError):
                self._plan = previous_plan
                self._journal = previous_journal
                self._fingerprints = previous_fingerprints
                raise

    def start(self, task_id: str) -> TaskItem:
        with self._lock:
            self._validate_sources()
            return super().start(task_id)

    def transition(
        self,
        task_id: str,
        status: TaskStatus,
        note: str = "",
    ) -> TaskItem:
        with self._lock:
            previous_plan = self._plan
            previous_journal = list(self._journal)
            previous_fingerprints = self._fingerprints
            try:
                if status is TaskStatus.COMPLETED:
                    current = self.get_task(task_id)
                    self._refresh_fingerprints(current.files)
                updated = super().transition(task_id, status, note)
                self._append("task_status", updated.task_id, updated.status.value, updated.note)
                self._save()
            except (OSError, RuntimeError, ValueError):
                self._plan = previous_plan
                self._journal = previous_journal
                self._fingerprints = previous_fingerprints
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
        self._repository.save(
            TaskCheckpoint(self._plan, tuple(self._journal), self._fingerprints)
        )

    def _snapshot_plan(self, plan: TaskPlan) -> tuple[TaskSourceFingerprint, ...]:
        if self._source_guard is None:
            return ()
        paths = tuple(path for item in plan.tasks for path in item.files)
        return self._source_guard.snapshot(paths)

    def _validate_sources(self) -> None:
        if self._source_guard is None or self._plan is None:
            return
        paths = tuple(dict.fromkeys(path for item in self._plan.tasks for path in item.files))
        if paths and not self._fingerprints:
            raise TaskSourceDriftError((), missing_baseline=True)
        expected_paths = {item.path for item in self._fingerprints}
        if set(paths) != expected_paths:
            raise TaskSourceDriftError((), missing_baseline=True)
        drifts = self._source_guard.compare(self._fingerprints)
        if drifts:
            raise TaskSourceDriftError(drifts)

    def _refresh_fingerprints(self, paths: tuple[str, ...]) -> None:
        if self._source_guard is None or not paths:
            return
        refreshed = {item.path: item for item in self._source_guard.snapshot(paths)}
        current = {item.path: item for item in self._fingerprints}
        current.update(refreshed)
        self._fingerprints = tuple(current[path] for path in sorted(current))
