from dataclasses import dataclass

from boru.tools.edit_models import EditOutcome, EditProposal
from boru.tools.write_models import WriteOutcome


@dataclass(frozen=True, slots=True)
class ProjectEditRequest:
    instruction: str

    def __post_init__(self) -> None:
        cleaned = self.instruction.strip()
        if not cleaned:
            raise ValueError("Proje düzenleme talimatı boş olamaz.")
        object.__setattr__(self, "instruction", cleaned)


@dataclass(frozen=True, slots=True)
class ProjectFileSelection:
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        cleaned = tuple(path.strip() for path in self.paths if path.strip())
        if not cleaned:
            raise ValueError("Proje düzenleme için en az bir dosya seçilmelidir.")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Proje düzenleme dosya seçimi tekrar içeremez.")
        object.__setattr__(self, "paths", cleaned)


@dataclass(frozen=True, slots=True)
class ProjectPatchSpec:
    path: str
    old_text: str
    new_text: str
    reason: str = ""

    def __post_init__(self) -> None:
        cleaned_path = self.path.strip()
        if not cleaned_path:
            raise ValueError("Project patch path boş olamaz.")
        if not self.old_text:
            raise ValueError("Project patch old_text boş olamaz.")
        if self.old_text == self.new_text:
            raise ValueError("Project patch eski ve yeni içerik aynı olamaz.")
        object.__setattr__(self, "path", cleaned_path)
        object.__setattr__(self, "reason", self.reason.strip())


@dataclass(frozen=True, slots=True)
class ProjectCreateSpec:
    path: str
    content: str
    reason: str = ""

    def __post_init__(self) -> None:
        cleaned_path = self.path.strip().strip("\"'")
        if not cleaned_path:
            raise ValueError("Project create path boş olamaz.")
        object.__setattr__(self, "path", cleaned_path)
        object.__setattr__(self, "reason", self.reason.strip())


@dataclass(frozen=True, slots=True)
class ProjectChangePlan:
    patches: tuple[ProjectPatchSpec, ...] = ()
    creations: tuple[ProjectCreateSpec, ...] = ()

    def __post_init__(self) -> None:
        if not self.patches and not self.creations:
            raise ValueError("Project plan en az bir değişiklik içermelidir.")


@dataclass(frozen=True, slots=True)
class ProjectEditProposal:
    instruction: str
    edits: tuple[EditProposal, ...] = ()
    creations: tuple[ProjectCreateSpec, ...] = ()

    def __post_init__(self) -> None:
        cleaned_instruction = self.instruction.strip()
        if not cleaned_instruction:
            raise ValueError("Proje düzenleme proposal talimatı boş olamaz.")
        if not self.edits and not self.creations:
            raise ValueError("Proje düzenleme proposal en az bir değişiklik içermelidir.")

        paths = tuple(edit.path for edit in self.edits) + tuple(
            creation.path for creation in self.creations
        )
        if len(paths) != len(set(paths)):
            raise ValueError(
                "Aynı dosya bir proje transaction içinde birden fazla kez hedeflenemez."
            )

        object.__setattr__(self, "instruction", cleaned_instruction)


@dataclass(frozen=True, slots=True)
class ProjectEditOutcome:
    outcomes: tuple[EditOutcome | WriteOutcome, ...]

    def __post_init__(self) -> None:
        if not self.outcomes:
            raise ValueError("Proje düzenleme sonucu en az bir dosya içermelidir.")
