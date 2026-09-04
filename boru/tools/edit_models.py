from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EditRequest:
    path: str
    old_text: str
    new_text: str

    def __post_init__(self) -> None:
        cleaned_path = self.path.strip().strip("\"'")

        if not cleaned_path:
            raise ValueError(
                "Düzenlenecek dosya yolu boş olamaz."
            )

        if not self.old_text:
            raise ValueError(
                "Değiştirilecek eski içerik boş olamaz."
            )

        if self.old_text == self.new_text:
            raise ValueError(
                "Eski ve yeni içerik aynı olamaz."
            )

        object.__setattr__(
            self,
            "path",
            cleaned_path,
        )


@dataclass(frozen=True, slots=True)
class EditProposal:
    path: str
    updated_content: str
    expected_sha256: str
    diff: str
    original_character_count: int
    updated_character_count: int


@dataclass(frozen=True, slots=True)
class EditOutcome:
    relative_path: str
    character_count: int
    byte_count: int