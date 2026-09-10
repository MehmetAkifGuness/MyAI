from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import time


class ReflectionVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True, slots=True)
class ReflectionRecord:
    id: str
    task: str
    verdict: ReflectionVerdict
    target_paths: tuple[str, ...]
    lesson: str
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "verdict": self.verdict.value,
            "target_paths": list(self.target_paths),
            "lesson": self.lesson,
            "timestamp": self.timestamp or time.time(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReflectionRecord:
        return cls(
            id=str(data.get("id", "")),
            task=str(data.get("task", "")),
            verdict=ReflectionVerdict(data.get("verdict", "PASS")),
            target_paths=tuple(data.get("target_paths", ())),
            lesson=str(data.get("lesson", "")),
            timestamp=float(data.get("timestamp", 0.0)),
        )
