import re
from collections.abc import Sequence
from threading import RLock

from boru.knowledge.models import KnowledgeDocument, KnowledgeHit
from boru.memory.contracts import EmbeddingProvider
from boru.memory.similarity import cosine_similarity


class HybridKnowledgeRetriever:
    _TOKEN_PATTERN = re.compile(r"[\wçğıöşü]+", re.IGNORECASE)

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        minimum_similarity: float = 0.40,
    ):
        if not 0.0 <= minimum_similarity <= 1.0:
            raise ValueError("minimum_similarity 0.0 ile 1.0 arasında olmalıdır.")
        self._embedding_provider = embedding_provider
        self._minimum_similarity = minimum_similarity
        self._cache: dict[str, list[float]] = {}
        self._lock = RLock()

    def retrieve(
        self,
        query: str,
        documents: Sequence[KnowledgeDocument],
        limit: int,
    ) -> list[KnowledgeHit]:
        if limit < 1:
            raise ValueError("limit en az 1 olmalıdır.")
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        candidates = [
            (document.source_path, chunk)
            for document in documents
            for chunk in document.chunks
        ]
        if not candidates:
            return []

        query_tokens = self._tokens(cleaned_query)
        lexical_scores = [
            self._lexical_score(query_tokens, chunk.text)
            for _, chunk in candidates
        ]
        semantic_scores = (
            [0.0] * len(candidates)
            if any(score > 0.0 for score in lexical_scores)
            else self._semantic_scores(cleaned_query, candidates)
        )

        hits: list[KnowledgeHit] = []
        for (source_path, chunk), lexical, semantic in zip(
            candidates, lexical_scores, semantic_scores
        ):
            if lexical <= 0.0 and semantic < self._minimum_similarity:
                continue
            score = (2.0 + lexical if lexical > 0.0 else 0.0) + semantic
            hits.append(KnowledgeHit(source_path, chunk, score))

        hits.sort(key=lambda hit: (hit.score, hit.source_path), reverse=True)
        return hits[:limit]

    def _semantic_scores(self, query, candidates) -> list[float]:
        if self._embedding_provider is None:
            return [0.0] * len(candidates)

        missing = self._prepare_cache(candidates)
        generated = self._generate_embeddings(query, missing)
        if generated is None:
            return [0.0] * len(candidates)
        query_vector, generated_chunks = generated

        with self._lock:
            for chunk, vector in zip(missing, generated_chunks):
                self._cache[chunk.chunk_id] = vector
            return [
                cosine_similarity(query_vector, self._cache[chunk.chunk_id])
                for _, chunk in candidates
            ]

    def _prepare_cache(self, candidates):
        valid_ids = {chunk.chunk_id for _, chunk in candidates}
        with self._lock:
            stale_ids = tuple(
                chunk_id for chunk_id in self._cache if chunk_id not in valid_ids
            )
            for chunk_id in stale_ids:
                del self._cache[chunk_id]
            return [chunk for _, chunk in candidates if chunk.chunk_id not in self._cache]

    def _generate_embeddings(self, query, missing):
        try:
            query_vectors = self._embedding_provider.embed([query])
            if len(query_vectors) != 1:
                raise RuntimeError("Embedding provider sorgu vektörü döndürmedi.")

            generated_chunks: list[list[float]] = []
            for start in range(0, len(missing), 32):
                batch = missing[start : start + 32]
                vectors = self._embedding_provider.embed([chunk.text for chunk in batch])
                if len(vectors) != len(batch):
                    raise RuntimeError("Embedding provider eksik vektör döndürdü.")
                generated_chunks.extend(vectors)
        except (RuntimeError, ValueError, TypeError, OSError, ConnectionError, TimeoutError):
            return None

        return query_vectors[0], generated_chunks

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        return {
            token.casefold()
            for token in cls._TOKEN_PATTERN.findall(value)
            if len(token) > 1
        }

    @classmethod
    def _lexical_score(cls, query_tokens: set[str], text: str) -> float:
        if not query_tokens:
            return 0.0
        document_tokens = cls._tokens(text)
        return len(query_tokens & document_tokens) / len(query_tokens)
