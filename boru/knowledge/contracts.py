from collections.abc import Sequence
from typing import Protocol

from boru.knowledge.models import KnowledgeDocument, KnowledgeHit


class KnowledgeRepository(Protocol):
    def load_all(self) -> list[KnowledgeDocument]:
        ...

    def save_all(self, documents: Sequence[KnowledgeDocument]) -> None:
        ...


class KnowledgeDocumentLoader(Protocol):
    def load(self, relative_path: str) -> tuple[str, str]:
        ...


class KnowledgeRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        documents: Sequence[KnowledgeDocument],
        limit: int,
    ) -> list[KnowledgeHit]:
        ...
