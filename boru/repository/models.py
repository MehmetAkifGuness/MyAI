from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepositoryProfile:
    root: str
    file_count: int
    languages: tuple[tuple[str, int], ...]
    frameworks: tuple[str, ...]
    package_managers: tuple[str, ...]
    entry_points: tuple[str, ...]
    test_files: tuple[str, ...]
    test_commands: tuple[str, ...]
    documentation: tuple[str, ...]
    ci_files: tuple[str, ...]
    license_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepositoryTaskContext:
    objective: str
    paths: tuple[str, ...]
    reasons: tuple[tuple[str, str], ...] = ()
