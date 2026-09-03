from collections.abc import Sequence
from typing import Protocol

from boru.memory.models import (
    MemoryDecision,
    MemoryForgetRequest,
    MemoryRecord,
    StructuredMemoryFact,
)


class MemoryRepository(Protocol):
    def load_all(
        self,
    ) -> list[MemoryRecord]:
        ...

    def save_all(
        self,
        memories: Sequence[MemoryRecord],
    ) -> None:
        ...


class MemoryExtractor(Protocol):
    def extract(
        self,
        user_message: str,
    ) -> list[str]:
        ...


class MemoryRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        memories: Sequence[MemoryRecord],
        limit: int,
    ) -> list[MemoryRecord]:
        ...


class EmbeddingProvider(Protocol):
    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        ...


class MemoryDecisionEngine(Protocol):
    def decide(
        self,
        user_message: str,
    ) -> MemoryDecision:
        ...


class MemoryDecisionGate(Protocol):
    def should_evaluate(
        self,
        user_message: str,
    ) -> bool:
        ...


class MemoryIntentDetector(Protocol):
    def is_memory_relevant(
        self,
        user_message: str,
    ) -> bool:
        ...


class MemoryForgetParser(Protocol):
    def parse(
        self,
        user_message: str,
    ) -> MemoryForgetRequest | None:
        ...


class MemoryStructurer(Protocol):
    def structure(
        self,
        content: str,
    ) -> StructuredMemoryFact | None:
        ...


class MemorySubjectMatcher(Protocol):
    def is_same_subject(
        self,
        left: str,
        right: str,
    ) -> bool:
        ...


class MemoryConflictResolver(Protocol):
    def find_existing(
        self,
        fact: StructuredMemoryFact,
        memories: Sequence[MemoryRecord],
    ) -> MemoryRecord | None:
        ...


class MemoryService(Protocol):
    def observe(
        self,
        user_message: str,
    ) -> list[MemoryRecord]:
        ...

    def build_context(
        self,
        query: str,
    ) -> str:
        ...

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        ...

    def list_recent(
        self,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        ...

    def forget_structured(
        self,
        subject: str,
        relation: str,
    ) -> MemoryRecord | None:
        ...

    def forget_subject(
        self,
        subject: str,
    ) -> list[MemoryRecord]:
        ...

    def forget_latest(
        self,
    ) -> MemoryRecord | None:
        ...

    def clear_all(
        self,
    ) -> list[MemoryRecord]:
        ...