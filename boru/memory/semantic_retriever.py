from collections.abc import Sequence
from threading import RLock

from boru.memory.contracts import (
    EmbeddingProvider,
)
from boru.memory.models import (
    MemoryRecord,
)
from boru.memory.similarity import (
    cosine_similarity,
)


class SemanticMemoryRetriever:
    """
    Embedding cosine similarity ile
    anlamsal hafıza araması yapar.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        minimum_similarity: float = 0.45,
    ):
        if not 0.0 <= minimum_similarity <= 1.0:
            raise ValueError(
                (
                    "minimum_similarity "
                    "0.0 ile 1.0 arasında "
                    "olmalıdır."
                )
            )

        self._embedding_provider = (
            embedding_provider
        )

        self._minimum_similarity = (
            minimum_similarity
        )

        self._cache: dict[
            tuple[str, str],
            list[float],
        ] = {}

        self._lock = RLock()

    def retrieve(
        self,
        query: str,
        memories: Sequence[MemoryRecord],
        limit: int,
    ) -> list[MemoryRecord]:
        if limit < 1:
            raise ValueError(
                "limit en az 1 olmalıdır."
            )

        cleaned_query = (
            query.strip()
        )

        if not cleaned_query or not memories:
            return []

        try:
            (
                query_vector,
                memory_vectors,
            ) = self._vectors_for_search(
                cleaned_query,
                memories,
            )

        except Exception:
            return []

        scored: list[
            tuple[
                float,
                MemoryRecord,
            ]
        ] = []

        for memory, memory_vector in zip(
            memories,
            memory_vectors,
        ):
            similarity = (
                cosine_similarity(
                    query_vector,
                    memory_vector,
                )
            )

            if (
                similarity
                < self._minimum_similarity
            ):
                continue

            scored.append(
                (
                    similarity,
                    memory,
                )
            )

        scored.sort(
            key=lambda item: (
                item[0],
                item[1].updated_at,
            ),
            reverse=True,
        )

        return [
            memory
            for _, memory
            in scored[:limit]
        ]

    def _vectors_for_search(
        self,
        query: str,
        memories: Sequence[MemoryRecord],
    ) -> tuple[
        list[float],
        list[list[float]],
    ]:
        with self._lock:
            missing_memories = [
                memory
                for memory in memories
                if (
                    self._cache_key(memory)
                    not in self._cache
                )
            ]

        inputs = [
            query
        ]

        inputs.extend(
            self._embedding_text(memory)
            for memory
            in missing_memories
        )

        generated = (
            self._embedding_provider
            .embed(inputs)
        )

        if len(generated) != len(inputs):
            raise RuntimeError(
                (
                    "Embedding provider "
                    "eksik vektör döndürdü."
                )
            )

        query_vector = generated[0]

        with self._lock:
            for memory, vector in zip(
                missing_memories,
                generated[1:],
            ):
                self._remove_stale_cache_entries(
                    memory.memory_id
                )

                self._cache[
                    self._cache_key(memory)
                ] = vector

            memory_vectors = [
                self._cache[
                    self._cache_key(memory)
                ]
                for memory
                in memories
            ]

        return (
            query_vector,
            memory_vectors,
        )

    def _remove_stale_cache_entries(
        self,
        memory_id: str,
    ) -> None:
        stale_keys = [
            key
            for key in self._cache
            if key[0] == memory_id
        ]

        for key in stale_keys:
            del self._cache[key]

    @staticmethod
    def _cache_key(
        memory: MemoryRecord,
    ) -> tuple[str, str]:
        return (
            memory.memory_id,
            memory.updated_at,
        )

    @staticmethod
    def _embedding_text(
        memory: MemoryRecord,
    ) -> str:
        parts = [
            (
                "İçerik: "
                f"{memory.content}"
            )
        ]

        if memory.subject:
            parts.append(
                (
                    "Konu: "
                    f"{memory.subject}"
                )
            )

        if memory.relation:
            relation = (
                memory.relation
                .replace(
                    "_",
                    " ",
                )
            )

            parts.append(
                (
                    "İlişki: "
                    f"{relation}"
                )
            )

        if memory.value:
            parts.append(
                (
                    "Değer: "
                    f"{memory.value}"
                )
            )

        return ". ".join(
            parts
        )