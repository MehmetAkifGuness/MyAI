import re
from collections import defaultdict

from boru.performance.monitor import PerformanceMonitor


class PerformanceStatusCoordinator:
    _REQUEST = re.compile(r"^\s*performans\s+(?:durumu|raporu)\s*[.!]?\s*$", re.IGNORECASE)

    def __init__(self, monitor: PerformanceMonitor) -> None:
        self._monitor = monitor

    def resolve(self, user_message: str) -> str | None:
        if self._REQUEST.fullmatch(user_message) is None:
            return None
        snapshot = self._monitor.snapshot()
        if not snapshot.metrics and not snapshot.counters:
            return "Henüz performans metriği oluşmadı."

        lines = ["PERFORMANS RAPORU"]
        grouped = defaultdict(list)
        for metric in snapshot.metrics:
            grouped[metric.operation].append(metric)
        for operation in sorted(grouped):
            values = grouped[operation]
            average = sum(item.duration_seconds for item in values) / len(values)
            last = values[-1]
            failures = sum(not item.succeeded for item in values)
            lines.append(
                f"- {operation}: son {last.duration_seconds:.2f} sn, "
                f"ortalama {average:.2f} sn, çağrı {len(values)}, hata {failures}"
            )
        if snapshot.counters:
            lines.append("Sayaçlar:")
            lines.extend(f"- {name}: {value}" for name, value in snapshot.counters)
        return "\n".join(lines)
