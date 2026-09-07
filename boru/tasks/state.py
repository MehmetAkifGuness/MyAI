from dataclasses import replace
from threading import RLock

from boru.tasks.models import TaskItem, TaskPlan, TaskStatus


class InMemoryTaskPlanState:
    _TRANSITIONS = {
        TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.BLOCKED},
        TaskStatus.RUNNING: {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.BLOCKED,
            TaskStatus.PENDING,
        },
        TaskStatus.FAILED: {TaskStatus.PENDING},
        TaskStatus.BLOCKED: {TaskStatus.PENDING, TaskStatus.COMPLETED},
        TaskStatus.COMPLETED: set(),
    }

    def __init__(self) -> None:
        self._plan: TaskPlan | None = None
        self._lock = RLock()

    def replace_plan(self, plan: TaskPlan) -> None:
        with self._lock:
            self._plan = plan

    def get_plan(self) -> TaskPlan | None:
        with self._lock:
            return self._plan

    def get_task(self, task_id: str) -> TaskItem:
        with self._lock:
            plan = self._require_plan()
            normalized = task_id.strip().upper()
            for item in plan.tasks:
                if item.task_id == normalized:
                    return item
        raise ValueError(f"Task bulunamadı: {task_id}")

    def start(self, task_id: str) -> TaskItem:
        with self._lock:
            item = self.get_task(task_id)
            plan = self._require_plan()
            statuses = {task.task_id: task.status for task in plan.tasks}
            incomplete = tuple(
                dependency
                for dependency in item.dependencies
                if statuses.get(dependency) is not TaskStatus.COMPLETED
            )
            if incomplete:
                raise ValueError(
                    f"{item.task_id} bağımlılıkları tamamlanmadı: "
                    + ", ".join(incomplete)
                )
            return self.transition(item.task_id, TaskStatus.RUNNING)

    def transition(
        self,
        task_id: str,
        status: TaskStatus,
        note: str = "",
        *,
        refresh_sources: bool = False,
    ) -> TaskItem:
        del refresh_sources
        with self._lock:
            current = self.get_task(task_id)
            if status not in self._TRANSITIONS[current.status]:
                raise ValueError(
                    f"Geçersiz task durumu geçişi: "
                    f"{current.status.value} -> {status.value}"
                )
            updated = replace(current, status=status, note=note)
            self._replace_task(updated)
            return updated

    def reset(self, task_id: str) -> TaskItem:
        return self.transition(task_id, TaskStatus.PENDING)

    def _replace_task(self, updated: TaskItem) -> None:
        plan = self._require_plan()
        tasks = tuple(
            updated if item.task_id == updated.task_id else item
            for item in plan.tasks
        )
        self._plan = replace(plan, tasks=tasks)

    def _require_plan(self) -> TaskPlan:
        if self._plan is None:
            raise ValueError("Henüz aktif bir task planı yok.")
        return self._plan
