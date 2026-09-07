import re
from threading import RLock

from boru.tasks.models import TaskStatus
from boru.tasks.workflow_guard import GuardedTaskWorkflow


class ReliableTaskCoordinator:
    """Recovery, inspection and explicit retry commands around the task workflow."""

    def __init__(self, coordinator, state, repository):
        self._coordinator = coordinator
        self._state = state
        self._repository = repository
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
        if self._state.get_task(task_id).status is not TaskStatus.FAILED:
            raise ValueError("Yalnızca failed task yeniden denenebilir.")
        self._state.validate_execution()
        self._state.reset(task_id)
        return self._coordinator.resolve(f"task çalıştır: {task_id}")

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
