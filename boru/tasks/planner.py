from boru.architecture.contracts import ArchitecturePlanner
from boru.architecture.request_parser import RuleBasedArchitectureRequestParser
from boru.tasks.models import TaskItem, TaskPlan


class ArchitectureTaskPlanner:
    """Grounded Architect planını sıralı ve bağımlı task grafiğine dönüştürür."""

    def __init__(
        self,
        architect: ArchitecturePlanner,
        request_parser: RuleBasedArchitectureRequestParser | None = None,
        max_tasks: int = 12,
    ) -> None:
        if max_tasks < 1:
            raise ValueError("Task planlayıcı sınırı pozitif olmalıdır.")
        self._architect = architect
        self._request_parser = request_parser or RuleBasedArchitectureRequestParser()
        self._max_tasks = max_tasks

    def plan(self, objective: str) -> TaskPlan:
        architecture = self._architect.plan(
            self._request_parser.parse_task(objective)
        )
        if len(architecture.steps) > self._max_tasks:
            raise ValueError("Architect planı task sayısı sınırını aştı.")

        tasks: list[TaskItem] = []
        for index, step in enumerate(architecture.steps, start=1):
            task_id = f"TASK-{index}"
            dependencies = (f"TASK-{index - 1}",) if index > 1 else ()
            description = (
                objective
                if len(architecture.steps) == 1
                else step.description
            )
            tasks.append(
                TaskItem(
                    task_id=task_id,
                    title=step.title,
                    description=description,
                    files=step.files,
                    dependencies=dependencies,
                )
            )
        return TaskPlan(objective, architecture.summary, tuple(tasks))
