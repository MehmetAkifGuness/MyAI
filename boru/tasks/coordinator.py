from threading import RLock

from boru.tasks.contracts import AgentWorkflow, TaskPlanner
from boru.tasks.models import TaskAction, TaskItem, TaskPlan, TaskStatus
from boru.tasks.parser import RuleBasedTaskCommandParser
from boru.tasks.state import InMemoryTaskPlanState


class TaskPlanCoordinator:
    _USAGE = (
        "Task sistemi biçimleri: 'görev planla: hedef', 'görev durumu', "
        "'task çalıştır: TASK-1', 'task sıfırla: TASK-1' veya "
        "'task tamamla: TASK-1'."
    )

    def __init__(
        self,
        *,
        parser: RuleBasedTaskCommandParser,
        planner: TaskPlanner,
        workflow: AgentWorkflow,
        state: InMemoryTaskPlanState | None = None,
    ) -> None:
        self._parser = parser
        self._planner = planner
        self._workflow = workflow
        self._state = state or InMemoryTaskPlanState()
        self._active_task_id: str | None = None
        self._lock = RLock()

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return self._workflow.has_pending

    def resolve(self, user_message: str) -> str | None:
        with self._lock:
            if self._workflow.has_pending:
                return self._continue_workflow(user_message)

            try:
                command = self._parser.parse(user_message)
            except ValueError as error:
                return f"Task sistemi isteği geçersiz: {error} {self._USAGE}"
            if command is None:
                if self._parser.is_task_intent(user_message):
                    return self._USAGE
                return self._workflow.resolve(user_message)

            if command.action is TaskAction.PLAN:
                return self._create_plan(command.value)
            if command.action is TaskAction.STATUS:
                return self._render_current_plan()
            if command.action is TaskAction.RUN:
                return self._start_task(command.value)
            if command.action is TaskAction.RESET:
                return self._reset_task(command.value)
            if command.action is TaskAction.COMPLETE:
                return self._complete_blocked_task(command.value)
            return self._USAGE

    def _create_plan(self, objective: str) -> str:
        try:
            plan = self._planner.plan(objective)
        except Exception as error:
            return f"Görev planı hazırlanamadı: {error}"
        self._state.replace_plan(plan)
        self._active_task_id = None
        return self._render_plan(plan, "GÖREV PLANI HAZIRLANDI")

    def _start_task(self, task_id: str) -> str:
        try:
            item = self._state.start(task_id)
        except ValueError as error:
            return f"Task başlatılamadı: {error}"

        response = self._workflow.resolve(f"ajan görevi: {self._task_prompt(item)}")
        if self._workflow.has_pending:
            self._active_task_id = item.task_id
            return f"TASK DURUMU\n{item.task_id}: running\n\n{response}"

        self._state.transition(
            item.task_id,
            TaskStatus.FAILED,
            "Ajan akışı başlatılamadı.",
        )
        return f"TASK DURUMU\n{item.task_id}: failed\n\n{response or 'Yanıt yok.'}"

    def _continue_workflow(self, user_message: str) -> str | None:
        response = self._workflow.resolve(user_message)
        if self._active_task_id is None or self._workflow.has_pending:
            return response

        task_id = self._active_task_id
        self._active_task_id = None
        overall = self._orchestrator_status(response or "")
        if overall == "TAMAMLANDI":
            status = TaskStatus.COMPLETED
            note = "Tüm ajan aşamaları başarıyla tamamlandı."
        elif overall == "İPTAL EDİLDİ":
            status = TaskStatus.PENDING
            note = "Kullanıcı ajan akışını iptal etti."
        elif overall == "İNCELEME GEREKLİ":
            status = TaskStatus.BLOCKED
            note = "Test, güvenlik veya review bulgusu insan incelemesi gerektiriyor."
        else:
            status = TaskStatus.FAILED
            note = "Ajan akışı başarıyla tamamlanamadı."
        updated = self._state.transition(task_id, status, note)
        return f"TASK DURUMU\n{updated.task_id}: {updated.status.value}\n\n{response}"

    def _reset_task(self, task_id: str) -> str:
        try:
            item = self._state.reset(task_id)
        except ValueError as error:
            return f"Task sıfırlanamadı: {error}"
        return f"TASK DURUMU\n{item.task_id}: pending"

    def _complete_blocked_task(self, task_id: str) -> str:
        try:
            current = self._state.get_task(task_id)
            if current.status is not TaskStatus.BLOCKED:
                raise ValueError("Yalnızca blocked durumundaki task kabul edilebilir.")
            item = self._state.transition(
                task_id,
                TaskStatus.COMPLETED,
                "Kullanıcı inceleme sonrasında sonucu kabul etti.",
            )
        except ValueError as error:
            return f"Task tamamlanamadı: {error}"
        return f"TASK DURUMU\n{item.task_id}: completed"

    def _render_current_plan(self) -> str:
        plan = self._state.get_plan()
        if plan is None:
            return "GÖREV DURUMU\nHenüz aktif bir task planı yok."
        return self._render_plan(plan, "GÖREV DURUMU")

    @staticmethod
    def _render_plan(plan: TaskPlan, header: str) -> str:
        lines = [
            header,
            f"Hedef: {plan.objective}",
            f"Özet: {plan.summary}",
            "Saklama: yalnızca bu uygulama oturumu",
            f"İlerleme: {sum(item.status is TaskStatus.COMPLETED for item in plan.tasks)}"
            f"/{len(plan.tasks)} tamamlandı",
        ]
        for item in plan.tasks:
            dependencies = ", ".join(item.dependencies) or "yok"
            files = ", ".join(item.files) or "belirtilmedi"
            lines.extend((
                "",
                f"- {item.task_id} [{item.status.value}] {item.title}",
                f"  {item.description}",
                f"  Dosyalar: {files}",
                f"  Bağımlılık: {dependencies}",
            ))
            if item.note:
                lines.append(f"  Not: {item.note}")
        return "\n".join(lines)

    @staticmethod
    def _task_prompt(item: TaskItem) -> str:
        prompt = f"{item.title}. {item.description}"
        if item.files:
            prompt += (
                " Yalnızca şu dosyaları kapsa: "
                + ", ".join(item.files)
                + "."
            )
        return prompt

    @staticmethod
    def _orchestrator_status(response: str) -> str:
        for line in response.splitlines():
            if line.startswith("Genel durum:"):
                return line.partition(":")[2].strip()
        return "BELİRSİZ"
