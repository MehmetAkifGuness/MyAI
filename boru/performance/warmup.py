from threading import Lock, Thread
from time import monotonic
from typing import Protocol

from boru.performance.monitor import PerformanceMonitor


class WarmableModel(Protocol):
    def warmup(self) -> None:
        ...


class ModelWarmupService:
    def __init__(self, model: WarmableModel, monitor: PerformanceMonitor) -> None:
        self._model = model
        self._monitor = monitor
        self._started = False
        self._lock = Lock()

    def start(self) -> bool:
        with self._lock:
            if self._started:
                return False
            self._started = True
        Thread(target=self._run, name="boru-model-warmup", daemon=True).start()
        return True

    def _run(self) -> None:
        started = monotonic()
        succeeded = False
        try:
            self._model.warmup()
            succeeded = True
        except Exception:
            self._monitor.increment("model.warmup.failure")
        finally:
            self._monitor.record("model.warmup", monotonic() - started, succeeded)
