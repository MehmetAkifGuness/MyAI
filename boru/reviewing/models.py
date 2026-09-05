from dataclasses import dataclass
from enum import IntEnum


class ReviewSeverity(IntEnum):
    INFO = 1
    WARNING = 2
    ERROR = 3


@dataclass(frozen=True, slots=True)
class CodeReviewRequest:
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized = tuple(
            path.strip().replace("\\", "/")
            for path in self.paths
            if path.strip()
        )
        if not normalized:
            raise ValueError("En az bir kaynak dosya belirtilmelidir.")
        if len(set(path.casefold() for path in normalized)) != len(normalized):
            raise ValueError("Aynı kaynak dosya birden fazla kez belirtilemez.")
        object.__setattr__(self, "paths", normalized)


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    path: str
    line: int
    rule: str
    severity: ReviewSeverity
    message: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class CodeReviewReport:
    reviewed_paths: tuple[str, ...]
    findings: tuple[ReviewFinding, ...]
    skipped_paths: tuple[str, ...] = ()

