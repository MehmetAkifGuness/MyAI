from dataclasses import dataclass
from enum import Enum
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    text: str
    line_start: int
    line_end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeChunk":
        chunk = cls(
            chunk_id=str(data.get("chunk_id", "")).strip(),
            text=str(data.get("text", "")).strip(),
            line_start=int(data.get("line_start", 0)),
            line_end=int(data.get("line_end", 0)),
        )
        if (
            not chunk.chunk_id
            or not chunk.text
            or chunk.line_start < 1
            or chunk.line_end < chunk.line_start
        ):
            raise ValueError("Geçersiz bilgi parçası.")
        return chunk


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    source_path: str
    content_sha256: str
    chunks: tuple[KnowledgeChunk, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "content_sha256": self.content_sha256,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeDocument":
        raw_chunks = data.get("chunks")
        if not isinstance(raw_chunks, list):
            raise ValueError("Bilgi belgesi parça listesi içermiyor.")
        document = cls(
            source_path=str(data.get("source_path", "")).strip(),
            content_sha256=str(data.get("content_sha256", "")).strip(),
            chunks=tuple(KnowledgeChunk.from_dict(item) for item in raw_chunks),
        )
        if (
            not document.source_path
            or re.fullmatch(r"[0-9a-f]{64}", document.content_sha256) is None
        ):
            raise ValueError("Geçersiz bilgi belgesi.")
        return document


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    source_path: str
    chunk: KnowledgeChunk
    score: float


class KnowledgeAction(str, Enum):
    ADD = "add"
    LIST = "list"
    DELETE = "delete"
    SEARCH = "search"
    ASK = "ask"


@dataclass(frozen=True, slots=True)
class KnowledgeRequest:
    action: KnowledgeAction
    value: str = ""
