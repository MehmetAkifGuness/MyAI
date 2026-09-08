import re
from threading import RLock

from boru.evaluation.models import Verdict
from boru.tasks.models import TaskStatus
from boru.tasks.workflow_guard import GuardedTaskWorkflow


class ReliableTaskCoordinator:
    """Recovery, inspection and explicit retry commands around the task workflow."""

    def __init__(self, coordinator, state, repository, *, evaluator=None, repair=None):
        self._coordinator = coordinator
        self._state = state
        self._repository = repository
        self._evaluator = evaluator
        self._repair = repair
        self._restore_pending = False
        self._lock = RLock()

    @property
    def has_pending(self):
        return self._restore_pending or self._coordinator.has_pending

    def resolve(self, message):
        with self._lock:
            try:
                return self._resolve(message)
            except (OSError, RuntimeError, ValueError) as error:
                return f"GÖREV İŞLEMİ DURDU\n{error}"
            finally:
                if self._repair is not None and not self.has_pending:
                    self._repair.clear()

    def _resolve(self, message):
        normalized = " ".join(message.strip().casefold().split())
        if self._restore_pending:
            return self._continue_restore(normalized)
        read_command = {
            "checkpoint durumu": self._repository.status,
            "plan sağlığı": self._state.health,
            "görev arşivi": self._repository.list_archives,
        }.get(normalized)
        if read_command is not None:
            return read_command()
        if self._coordinator.has_pending:
            return self._coordinator.resolve(message)
        if self._repair is not None:
            match = re.fullmatch(r"task (teşhis|onar):\s*(task-[1-9]\d*)", normalized)
            if match:
                return self._repair.run(match.group(2).upper(), repair=match.group(1) == "onar")
        if normalized == "checkpoint geri yükle":
            response = self._repository.prepare_restore()
            self._restore_pending = True
            return response
        if normalized == "checkpoint geri yüklemeyi onayla":
            return "Onay bekleyen checkpoint geri yükleme önerisi yok."
        if normalized == "planı arşivle":
            return "Görev planı arşivlendi: " + self._state.archive()
        match = re.fullmatch(r"task yeniden dene:\s*(task-[1-9]\d*)", normalized)
        if match:
            return self._retry(match.group(1).upper())
        if normalized.startswith(("checkpoint", "plan sağlığı", "görev arşivi", "task yeniden dene")):
            return "Biçimler: checkpoint durumu; checkpoint geri yükle; plan sağlığı; görev arşivi; task yeniden dene: TASK-1"
        try:
            return self._coordinator.resolve(message)
        except (OSError, RuntimeError, ValueError) as error:
            return GuardedTaskWorkflow.failure(error)

    def _retry(self, task_id):
        task = self._state.get_task(task_id)
        if task.status is not TaskStatus.FAILED:
            raise ValueError("Yalnızca failed task yeniden denenebilir.")
        self._state.ensure_attempt_available(task_id)
        if "[CHANGES_APPLIED]" in task.note and self._evaluator is not None:
            return self._retry_applied_change(task)
        self._state.reset(task_id)
        return self._coordinator.resolve(f"task çalıştır: {task_id}")

    def _retry_applied_change(self, task):
        # Keep the applied marker in both checkpoints if the process stops mid-retry.
        self._state.transition(task.task_id, TaskStatus.PENDING, task.note)
        self._state.transition(task.task_id, TaskStatus.RUNNING, task.note)
        try:
            report = self._evaluator.evaluate(task.files)
            self._state.validate_execution()
            if not self._evaluator.is_current(report):
                raise ValueError("[SOURCE_DRIFT] Doğrulama kanıtı güncel değil.")
        except (OSError, RuntimeError, ValueError):
            self._state.transition(task.task_id, TaskStatus.FAILED, task.note)
            raise
        if report.verdict is not Verdict.PASS:
            self._state.transition(task.task_id, TaskStatus.FAILED, task.note)
            return (
                "TASK YENİDEN DENEME\nDurum: DOĞRULAMA BAŞARISIZ\n"
                "Kod daha önce uygulandı; aynı patch yeniden uygulanmadı. "
                "Test sözleşmesini veya hedefi inceleyip yeni plan oluşturun.\n\n"
                + report.render()
            )
        completed = self._state.transition(
            task.task_id,
            TaskStatus.COMPLETED,
            "Uygulanmış değişiklik yeniden doğrulandı; tüm kontroller geçti.",
        )
        return (
            f"TASK YENİDEN DENEME\nDurum: TAMAMLANDI\n{completed.task_id}: completed\n\n"
            + report.workflow_report()
        )

    def _continue_restore(self, normalized):
        if normalized == "iptal":
            self._restore_pending = False
            self._repository.cancel_restore()
            return "Checkpoint geri yüklemesi iptal edildi."
        if normalized != "checkpoint geri yüklemeyi onayla":
            return "Geri yükleme onay bekliyor: 'checkpoint geri yüklemeyi onayla' veya 'iptal'."
        self._restore_pending = False
        preserved = self._repository.restore()
        self._state.reload_after_restore()
        return (
            "Checkpoint geri yüklendi; eski onaylar geçersizdir.\n"
            f"Önceki checkpoint korundu: {preserved or 'ana dosya yoktu'}\n"
            + self._state.health()
        )
