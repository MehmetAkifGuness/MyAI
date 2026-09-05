from collections import Counter, deque
from threading import RLock

from boru.performance.models import PerformanceMetric, PerformanceSnapshot


class PerformanceMonitor:
    def __init__(self, max_metrics: int = 100) -> None:
        if max_metrics < 1:
            raise ValueError("max_metrics en az 1 olmalıdır.")
        self._metrics: deque[PerformanceMetric] = deque(maxlen=max_metrics)
        self._counters: Counter[str] = Counter()
        self._lock = RLock()

    def record(self, operation: str, duration_seconds: float, succeeded: bool) -> None:
        name = operation.strip()
        if not name or duration_seconds < 0:
            raise ValueError("Performans metriği geçersiz.")
        with self._lock:
            self._metrics.append(PerformanceMetric(name, duration_seconds, succeeded))

    def increment(self, counter: str) -> None:
        name = counter.strip()
        if not name:
            raise ValueError("Performans sayacı boş olamaz.")
        with self._lock:
            self._counters[name] += 1

    def snapshot(self) -> PerformanceSnapshot:
        with self._lock:
            return PerformanceSnapshot(
                metrics=tuple(self._metrics),
                counters=tuple(sorted(self._counters.items())),
            )
