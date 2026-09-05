from dataclasses import dataclass
from enum import IntEnum


class SecuritySeverity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True, slots=True)
class SecurityScanRequest:
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
class SecurityFinding:
    path: str
    line: int
    rule: str
    severity: SecuritySeverity
    message: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class SecurityScanReport:
    scanned_paths: tuple[str, ...]
    findings: tuple[SecurityFinding, ...]
    skipped_paths: tuple[str, ...] = ()

