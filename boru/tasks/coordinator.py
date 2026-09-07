import re
from threading import RLock

from boru.tasks.contracts import AgentWorkflow, TaskPlanner
from boru.tasks.models import TaskAction, TaskItem, TaskPlan, TaskStatus
from boru.tasks.parser import RuleBasedTaskCommandParser
from boru.tasks.state import InMemoryTaskPlanState
from boru.tasks.journal_reporting import render_task_journal


class TaskPlanCoordinator:
    _USAGE = (
        "Task sistemi biçimleri: 'görev planla: hedef', 'görev durumu', 'görev günlüğü', "
        "'planı çalıştır', 'task çalıştır: TASK-1', 'task sıfırla: TASK-1' veya "
        "'task tamamla: TASK-1'."
    )
    _EXPLICIT_SCOPE = re.compile(
        r"\b(?:yalnızca|sadece)\b.*\bdosya\w*\b",
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(
        self,
        *,
        parser: RuleBasedTaskCommandParser,
        planner: TaskPlanner,
        workflow: AgentWorkflow,
        state: InMemoryTaskPlanState | None = None,
        planned_execution_enabled: bool = False,
    ) -> None:
        self._parser = parser
        self._planner = planner
        self._workflow = workflow
        self._state = state or InMemoryTaskPlanState()
        self._planned_execution_enabled = planned_execution_enabled
        self._active_task_id: str | None = None
        self._plan_run_active = False
        self._lock = RLock()

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return self._workflow.has_pending

    def resolve(self, user_message: str) -> str | None:
        with self._lock:
            try:
                command = self._parser.parse(user_message)
            except ValueError as error:
                return f"Task sistemi isteği geçersiz: {error} {self._USAGE}"
            if self._workflow.has_pending:
                if command is not None and command.action in {TaskAction.STATUS, TaskAction.JOURNAL}:
                    return self._dispatch(command.action, command.value)
                return self._continue_workflow(user_message)
            if command is None:
                if self._parser.is_task_intent(user_message):
                    return self._USAGE
                return self._workflow.resolve(user_message)
            return self._dispatch(command.action, command.value)

    def _dispatch(self, action: TaskAction, value: str) -> str:
        if action is TaskAction.PLAN:
            return self._create_plan(value)
        if action is TaskAction.STATUS:
            return self._render_current_plan()
        if action is TaskAction.JOURNAL:
            return self._render_journal()
        if action is TaskAction.RUN:
            return self._start_task(value)
        if action is TaskAction.RUN_PLAN:
            return self._start_plan()
        if action is TaskAction.RESET:
            return self._reset_task(value)
        if action is TaskAction.COMPLETE:
            return self._complete_blocked_task(value)
        return self._USAGE

    def _create_plan(self, objective: str) -> str:
        try:
            plan = self._planner.plan(objective)
            self._state.replace_plan(plan)
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            return f"Görev planı hazırlanamadı: {error}"
        self._active_task_id = None
        self._plan_run_active = False
        return self._render_plan(plan, "GÖREV PLANI HAZIRLANDI")

    def _start_plan(self) -> str:
        if not self._planned_execution_enabled:
            return "Planlı görev yürütme bu sürümde etkin değil."
        plan = self._state.get_plan()
        if plan is None:
            return "Planlı görev yürütme başlatılamadı: Henüz aktif bir task planı yok."
        next_task = self._next_ready_task(plan)
        if next_task is None:
            if all(item.status is TaskStatus.COMPLETED for item in plan.tasks):
                return self._render_plan_run("TAMAMLANDI", "Tüm tasklar zaten tamamlandı.")
            return self._render_plan_run(
                "BAŞLATILAMADI",
                "Çalıştırılabilir pending task yok; failed veya blocked taskları inceleyin.",
            )
        self._plan_run_active = True
        response = self._start_task(next_task.task_id)
        if not self._workflow.has_pending:
            updated = self._state.get_task(next_task.task_id)
            return self._continue_plan(updated, response)
        return self._render_plan_run(
            "ONAY BEKLİYOR",
            response,
            task_id=next_task.task_id,
        )

    def _start_task(self, task_id: str) -> str:
        try:
            item = self._state.start(task_id)
        except (OSError, RuntimeError, ValueError) as error:
            return f"Task başlatılamadı: {error}"

        response = self._workflow.resolve(
            f"ajan görevi: {self._task_prompt(item)}"
        )
        if self._workflow.has_pending:
            self._active_task_id = item.task_id
            return f"TASK DURUMU\n{item.task_id}: running\n\n{response}"

        response_text = response or ""
        overall = self._orchestrator_status(response_text)
        if overall == "TAMAMLANDI":
            updated = self._state.transition(
                item.task_id,
                TaskStatus.COMPLETED,
                "Hedef zaten sağlandı; doğrulamalar başarıyla tamamlandı.",
            )
        else:
            updated = self._state.transition(
                item.task_id,
                TaskStatus.FAILED,
                "Ajan akışı başlatılamadı." if not response else self._failure_note(response),
            )
        return (
            f"TASK DURUMU\n{item.task_id}: {updated.status.value}\n\n"
            f"{response or 'Yanıt yok.'}"
        )

    def _continue_workflow(self, user_message: str) -> str | None:
        response = self._workflow.resolve(user_message)
        if self._active_task_id is None or self._workflow.has_pending:
            return response

        task_id = self._active_task_id
        self._active_task_id = None
        response_text = response or ""
        overall = self._orchestrator_status(response_text)
        changes_applied = self._phase_status(response_text, "Coding") == "TAMAMLANDI"
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
            note = self._failure_note(response_text)
        if changes_applied and status is not TaskStatus.COMPLETED:
            note = "[CHANGES_APPLIED] " + note
        updated = self._state.transition(
            task_id,
            status,
            note,
            refresh_sources=changes_applied,
        )
        task_response = f"TASK DURUMU\n{updated.task_id}: {updated.status.value}\n\n{response}"
        if not self._plan_run_active:
            return task_response
        return self._continue_plan(updated, task_response)

    def _continue_plan(self, updated: TaskItem, task_response: str) -> str:
        if updated.status is not TaskStatus.COMPLETED:
            self._plan_run_active = False
            return self._render_plan_run("DURDU", task_response, task_id=updated.task_id)
        plan = self._state.get_plan()
        if plan is None or all(item.status is TaskStatus.COMPLETED for item in plan.tasks):
            self._plan_run_active = False
            return self._render_plan_run("TAMAMLANDI", task_response)
        next_task = self._next_ready_task(plan)
        if next_task is None:
            self._plan_run_active = False
            return self._render_plan_run("DURDU", task_response)
        next_response = self._start_task(next_task.task_id)
        if not self._workflow.has_pending:
            self._plan_run_active = False
            return self._render_plan_run("DURDU", task_response + "\n\n" + next_response)
        return self._render_plan_run(
            "SONRAKİ ADIM ONAY BEKLİYOR",
            task_response + "\n\n" + next_response,
            task_id=next_task.task_id,
        )

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
        report = self._render_plan(plan, "GÖREV DURUMU")
        if self._plan_run_active:
            report += f"\nPlan yürütme: aktif ({self._active_task_id or 'task bekleniyor'})"
        return report

    def _render_journal(self) -> str:
        return render_task_journal(self._state)

    @staticmethod
    def _next_ready_task(plan: TaskPlan) -> TaskItem | None:
        completed = {
            item.task_id for item in plan.tasks if item.status is TaskStatus.COMPLETED
        }
        return next(
            (
                item
                for item in plan.tasks
                if item.status is TaskStatus.PENDING
                and set(item.dependencies).issubset(completed)
            ),
            None,
        )

    @staticmethod
    def _render_plan_run(status: str, detail: str, *, task_id: str = "") -> str:
        lines = ["PLANLI GÖREV YÜRÜTME", f"Durum: {status}"]
        if task_id:
            lines.append(f"Aktif task: {task_id}")
        lines.extend(("", detail))
        return "\n".join(lines)

    def _render_plan(self, plan: TaskPlan, header: str) -> str:
        checkpoint_path = getattr(self._state, "checkpoint_path", None)
        storage = (
            f"kalıcı checkpoint ({checkpoint_path})"
            if checkpoint_path is not None
            else "yalnızca bu uygulama oturumu"
        )
        lines = [
            header,
            f"Hedef: {plan.objective}",
            f"Özet: {plan.summary}",
            f"Saklama: {storage}",
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

    def _task_prompt(self, item: TaskItem) -> str:
        prompt = item.description
        if item.files and self._planned_execution_enabled:
            prompt += "\nBORU_DOSYA_KAPSAMI: " + ", ".join(item.files)
        elif item.files and self._EXPLICIT_SCOPE.search(prompt) is None:
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

    @staticmethod
    def _phase_status(response: str, phase: str) -> str:
        prefix = f"- {phase}:"
        for line in response.splitlines():
            if line.startswith(prefix):
                return line.partition(":")[2].strip()
        return "BELİRSİZ"

    @staticmethod
    def _failure_note(response):
        if "- Test: BAŞARISIZ" in response:
            return "[TEST_FAILED] Uygulama sonrası test doğrulaması başarısız."
        for code in ("TIMEOUT", "IO_ERROR", "VALIDATION_ERROR", "RECOVERY_REQUIRED", "SOURCE_DRIFT"):
            if f"[{code}]" in response:
                return f"[{code}] Ajan akışı başlatılamadı; plan sağlığı ve servis durumunu inceleyin."
        return "[PROPOSAL_FAILED] Ajan önerisi hazırlanamadı; kapsam ve model çıktısını inceleyin."
