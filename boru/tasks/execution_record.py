import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskExecutionRecord:
    created_at: float
    attempts: tuple[tuple[str, int], ...] = ()

    def __post_init__(self):
        if (
            isinstance(self.created_at, bool)
            or not isinstance(self.created_at, (int, float))
            or not math.isfinite(self.created_at)
            or self.created_at <= 0
        ):
            raise ValueError("Plan oluşturma zamanı geçersiz.")
        keys = [key for key, _ in self.attempts]
        if len(keys) != len(set(keys)) or len(keys) > 12:
            raise ValueError("Task deneme kayıtları geçersiz.")
        for key, count in self.attempts:
            if not isinstance(key, str) or type(count) is not int or not 0 <= count <= 3:
                raise ValueError("Task deneme sayısı geçersiz.")

    def to_dict(self):
        return {"created_at": self.created_at, "attempts": dict(self.attempts)}

    @classmethod
    def from_dict(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"created_at", "attempts"}:
            raise ValueError("Checkpoint yürütme kaydı geçersiz.")
        attempts = value["attempts"]
        if not isinstance(attempts, dict):
            raise ValueError("Checkpoint deneme kaydı nesne olmalıdır.")
        return cls(value["created_at"], tuple(attempts.items()))
