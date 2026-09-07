from boru.tasks.models import TaskStatus
from boru.tasks.source_guard import TaskSourceDriftError


class GuardedTaskWorkflow:
    """Pre-approval validity checks and bounded, non-replaying failure handling."""

    def __init__(self, workflow, state):
        self._workflow = workflow
        self._state = state
        self._unavailable = False

    @property
    def has_pending(self):
        return not self._unavailable and self._workflow.has_pending

    def resolve(self, message):
        if self._unavailable:
            return "ORKESTRATÖR RAPORU\nGenel durum: BAŞLATILAMADI\n[RECOVERY_REQUIRED] Yeniden başlatın."
        try:
            if message.strip().casefold() == "kod değişikliğini onayla":
                plan = self._state.get_plan()
                if plan and any(task.status is TaskStatus.RUNNING for task in plan.tasks):
                    self._state.validate_execution()
            return self._workflow.resolve(message)
        except (OSError, RuntimeError, ValueError) as error:
            self._cancel()
            return self.failure(error)

    def _cancel(self):
        try:
            if self._workflow.has_pending:
                self._workflow.resolve("iptal")
            self._unavailable = self._workflow.has_pending
        except (OSError, RuntimeError, ValueError):
            self._unavailable = True

    @staticmethod
    def failure(error):
        if isinstance(error, TaskSourceDriftError):
            code, advice = "SOURCE_DRIFT", str(error)
        elif isinstance(error, TimeoutError):
            code, advice = "TIMEOUT", "İşlem süresi doldu; servis durumunu kontrol edip task'ı yeniden deneyin."
        elif isinstance(error, OSError):
            code, advice = "IO_ERROR", "Dosya/servis erişimi başarısız; erişimi kontrol edin."
        else:
            code, advice = "VALIDATION_ERROR", "Kapsam, checkpoint ve plan sağlığını kontrol edin."
        return f"ORKESTRATÖR RAPORU\nGenel durum: BAŞARISIZ\n[{code}] {advice}"
