from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrchestrationRequest:
    task: str

    def __post_init__(self) -> None:
        normalized = self.task.strip()
        if not normalized:
            raise ValueError("Ajan görevi boş olamaz.")
        object.__setattr__(self, "task", normalized)

