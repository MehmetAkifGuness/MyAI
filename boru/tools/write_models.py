from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WriteRequest:
    path: str
    content: str

    def __post_init__(self) -> None:
        cleaned_path = self.path.strip().strip("\"'")

        if not cleaned_path:
            raise ValueError(
                "Yazılacak dosya yolu boş olamaz."
            )

        object.__setattr__(
            self,
            "path",
            cleaned_path,
        )


@dataclass(frozen=True, slots=True)
class WriteOutcome:
    relative_path: str
    character_count: int
    byte_count: int