from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True, slots=True)
class StructuredMemoryFact:
    subject: str
    relation: str
    value: str


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    content: str
    fact: StructuredMemoryFact | None = None


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    content: str
    created_at: str
    updated_at: str
    subject: str | None = None
    relation: str | None = None
    value: str | None = None

    @property
    def fact(self) -> StructuredMemoryFact | None:
        if not self.subject or not self.relation or not self.value:
            return None

        return StructuredMemoryFact(
            subject=self.subject,
            relation=self.relation,
            value=self.value,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "subject": self.subject,
            "relation": self.relation,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        memory_id = str(data.get("memory_id", "")).strip()
        content = str(data.get("content", "")).strip()
        created_at = str(data.get("created_at", "")).strip()
        updated_at = str(data.get("updated_at", created_at)).strip()

        subject = cls._optional_text(data.get("subject"))
        relation = cls._optional_text(data.get("relation"))
        value = cls._optional_text(data.get("value"))

        if not memory_id or not content or not created_at or not updated_at:
            raise ValueError("Geçersiz uzun süreli hafıza kaydı.")

        structured_values = (subject, relation, value)
        if any(structured_values) and not all(structured_values):
            raise ValueError("Eksik yapılandırılmış hafıza alanı.")

        return cls(
            memory_id=memory_id,
            content=content,
            created_at=created_at,
            updated_at=updated_at,
            subject=subject,
            relation=relation,
            value=value,
        )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None

        cleaned = str(value).strip()
        return cleaned or None


@dataclass(frozen=True, slots=True)
class MemoryDecision:
    should_save: bool
    content: str | None = None
    reason: str = ""
    subject: str | None = None
    relation: str | None = None
    value: str | None = None

    @property
    def fact(self) -> StructuredMemoryFact | None:
        if not self.subject or not self.relation or not self.value:
            return None

        return StructuredMemoryFact(
            subject=self.subject,
            relation=self.relation,
            value=self.value,
        )


class MemoryForgetMode(str, Enum):
    TARGETED = "targeted"
    SUBJECT = "subject"
    LATEST = "latest"
    ALL = "all"
    CONFIRM_ALL = "confirm_all"
    CANCEL = "cancel"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class MemoryForgetRequest:
    mode: MemoryForgetMode
    subject: str | None = None
    relation: str | None = None