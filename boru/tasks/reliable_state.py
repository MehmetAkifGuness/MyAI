import time
from dataclasses import replace

from boru.tasks.checkpoint import TaskCheckpoint
from boru.tasks.execution_record import TaskExecutionRecord
from boru.tasks.models import TaskStatus
from boru.tasks.persistent_state import PersistentTaskPlanState


class ReliableTaskPlanState(PersistentTaskPlanState):
    MAX_ATTEMPTS = 3
    MAX_PLAN_AGE = 7 * 24 * 60 * 60

    def __init__(self, repository, source_guard, *, clock=time.time):
        self._clock = clock
        super().__init__(repository, source_guard)

    def replace_plan(self, plan):
        with self._lock:
            self._repository.ensure_writable()
            if self._plan and any(task.status is TaskStatus.RUNNING for task in self._plan.tasks):
                raise ValueError("Çalışan görev bitmeden yeni plan oluşturulamaz.")
            # Validate all paths before archiving/replacing the current plan.
            self._snapshot_plan(plan)
            if self._plan:
                self._repository.archive_current(self._checkpoint())
            previous = self._execution
            self._execution = TaskExecutionRecord(self._clock())
            try:
                super().replace_plan(plan)
            except (OSError, RuntimeError, ValueError):
                self._execution = previous
                raise

    def validate_execution(self):
        self._repository.ensure_writable()
        if not self._plan:
            raise ValueError("Henüz aktif bir task planı yok.")
        if self._execution is None:
            raise ValueError("[PLAN_EXPIRED] Eski planın zaman kaydı yok; görevi yeniden planlayın.")
        age = self._clock() - self._execution.created_at
        if age < -60 or age > self.MAX_PLAN_AGE:
            raise ValueError("[PLAN_EXPIRED] Planın 7 günlük geçerlilik süresi doldu; yeniden planlayın.")
        self._validate_sources()

    def start(self, task_id):
        with self._lock:
            self.validate_execution()
            return super().start(task_id)

    def ensure_attempt_available(self, task_id):
        with self._lock:
            self.validate_execution()
            task = self.get_task(task_id)
            if self.remaining_attempts(task_id) == 0:
                raise ValueError("[RETRY_LIMIT] Task başına en fazla 3 deneme; yeni plan gerekli.")
            if any(self.get_task(key).status is not TaskStatus.COMPLETED for key in task.dependencies):
                raise ValueError("Task bağımlılıkları tamamlanmadı.")

    def remaining_attempts(self, task_id):
        with self._lock:
            self.validate_execution()
            self.get_task(task_id)
            used = dict(self._execution.attempts).get(task_id, 0)
            return max(0, self.MAX_ATTEMPTS - used)

    def transition(self, task_id, status, note="", *, refresh_sources=False):
        with self._lock:
            self._repository.ensure_writable()
            previous = self._execution
            if status is TaskStatus.RUNNING:
                self.validate_execution()
                attempts = dict(self._execution.attempts)
                count = attempts.get(task_id, 0)
                if count >= self.MAX_ATTEMPTS:
                    raise ValueError("[RETRY_LIMIT] Task başına en fazla 3 deneme; yeni plan gerekli.")
                attempts[task_id] = count + 1
                self._execution = replace(self._execution, attempts=tuple(attempts.items()))
            if status is TaskStatus.COMPLETED and self.get_task(task_id).status is TaskStatus.BLOCKED:
                # A manual acceptance must not bless source drift or expired plans.
                self.validate_execution()
            try:
                return super().transition(
                    task_id,
                    status,
                    note,
                    refresh_sources=refresh_sources,
                )
            except (OSError, RuntimeError, ValueError):
                self._execution = previous
                raise

    def reload_after_restore(self):
        with self._lock:
            checkpoint = self._repository.load()
            self._plan = checkpoint.plan
            self._journal = list(checkpoint.journal)
            self._fingerprints = checkpoint.fingerprints
            self._execution = checkpoint.execution
            self._recover_interrupted_tasks()

    def _checkpoint(self):
        return TaskCheckpoint(self._plan, tuple(self._journal), self._fingerprints, self._execution)

    def archive(self):
        with self._lock:
            plan = self._require_plan()
            if not all(task.status is TaskStatus.COMPLETED for task in plan.tasks):
                raise ValueError("Yalnızca tamamlanmış plan arşivlenebilir.")
            identifier = self._repository.archive_current(self._checkpoint())
            self._repository.save(TaskCheckpoint(None))
            self._plan = None
            self._journal = []
            self._fingerprints = ()
            self._execution = None
            return identifier

    def health(self):
        with self._lock:
            try:
                self.validate_execution()
                result = "Durum: GEÇERLİ"
            except (OSError, RuntimeError, ValueError) as error:
                result = f"Durum: DURDU\n{error}"
            counts = dict(self._execution.attempts) if self._execution else {}
            lines = ["PLAN SAĞLIĞI", result, "Geçerlilik: 7 gün; deneme sınırı: task başına 3."]
            for task in self._plan.tasks if self._plan else ():
                lines.append(f"- {task.task_id}: {task.status.value}, deneme {counts.get(task.task_id, 0)}/3")
            return "\n".join(lines)
