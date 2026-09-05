from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PerformanceMetric:
    operation: str
    duration_seconds: float
    succeeded: bool


@dataclass(frozen=True, slots=True)
class PerformanceSnapshot:
    metrics: tuple[PerformanceMetric, ...]
    counters: tuple[tuple[str, int], ...]
