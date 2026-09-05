from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArchitectureRequest:
    task: str

    def __post_init__(self) -> None:
        cleaned = self.task.strip()
        if not cleaned:
            raise ValueError("Mimari görev boş olamaz.")
        object.__setattr__(self, "task", cleaned)


@dataclass(frozen=True, slots=True)
class ArchitectureStep:
    title: str
    description: str
    files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        title = self.title.strip()
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
