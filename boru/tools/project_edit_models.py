from dataclasses import dataclass

from boru.tools.edit_models import (
    EditOutcome,
    EditProposal,
)


@dataclass(frozen=True, slots=True)
class ProjectEditRequest:
    instruction: str

    def __post_init__(self) -> None:
        cleaned = self.instruction.strip()

        if not cleaned:
            raise ValueError(
                "Proje düzenleme talimatı boş olamaz."
            )

        object.__setattr__(
            self,
            "instruction",
            cleaned,
        )


@dataclass(frozen=True, slots=True)
class ProjectFileSelection:
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        cleaned = tuple(
            path.strip()
            for path in self.paths
            if path.strip()
        )

        if not cleaned:
            raise ValueError(
                "Proje düzenleme için en az bir dosya seçilmelidir."
            )

        if len(cleaned) != len(set(cleaned)):
            raise ValueError(
                "Proje düzenleme dosya seçimi tekrar içeremez."
            )

        object.__setattr__(
            self,
            "paths",
            cleaned,
        )


@dataclass(frozen=True, slots=True)
class ProjectEditProposal:
    instruction: str
    edits: tuple[EditProposal, ...]

    def __post_init__(self) -> None:
        cleaned_instruction = self.instruction.strip()

        if not cleaned_instruction:
            raise ValueError(
                "Proje düzenleme proposal talimatı boş olamaz."
            )

        if not self.edits:
            raise ValueError(
                "Proje düzenleme proposal en az bir edit içermelidir."
            )

        paths = tuple(
            edit.path
            for edit in self.edits
        )

        if len(paths) != len(set(paths)):
            raise ValueError(
                "Aynı dosya bir proje düzenleme proposal içinde iki kez değiştirilemez."
            )

        object.__setattr__(
            self,
            "instruction",
            cleaned_instruction,
        )


@dataclass(frozen=True, slots=True)
class ProjectEditOutcome:
    outcomes: tuple[EditOutcome, ...]

    def __post_init__(self) -> None:
        if not self.outcomes:
            raise ValueError(
                "Proje düzenleme sonucu en az bir dosya içermelidir."
            )