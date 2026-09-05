import re
from dataclasses import dataclass


_STEP_NUMBER_PREFIX = re.compile(
    r"^(?:(?:adım\s*)?\d+\s*[.):\-]\s*)+",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ArchitectureRequest:
    task: str
    file_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        cleaned = self.task.strip()
        if not cleaned:
            raise ValueError("Mimari görev boş olamaz.")
        normalized_scope = tuple(
            dict.fromkeys(
                path.strip().replace("\\", "/")
                for path in self.file_scope
                if path.strip()
            )
        )
        object.__setattr__(self, "task", cleaned)
        object.__setattr__(self, "file_scope", normalized_scope)


@dataclass(frozen=True, slots=True)
class ArchitectureStep:
    title: str
    description: str
    files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        title = _STEP_NUMBER_PREFIX.sub("", self.title.strip()).strip()
        description = self.description.strip()
        files = tuple(path.strip() for path in self.files if path.strip())
        if not title or not description:
            raise ValueError("Mimari plan adımı başlık ve açıklama içermelidir.")
        if len(files) != len(set(files)):
            raise ValueError("Mimari plan adımı yinelenen dosya içeremez.")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "files", files)


@dataclass(frozen=True, slots=True)
class ArchitecturePlan:
    summary: str
    existing_files: tuple[str, ...]
    new_files: tuple[str, ...]
    steps: tuple[ArchitectureStep, ...]
    risks: tuple[str, ...]
    tests: tuple[str, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        summary = self.summary.strip()
        if not summary:
            raise ValueError("Mimari plan özeti boş olamaz.")
        if not self.steps:
            raise ValueError("Mimari plan en az bir adım içermelidir.")
        for values, label in (
            (self.existing_files, "mevcut dosya"),
            (self.new_files, "yeni dosya"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Mimari plan yinelenen {label} içeremez.")
        normalized_new = tuple(
            path for path in self.new_files if path not in set(self.existing_files)
        )
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "new_files", normalized_new)
