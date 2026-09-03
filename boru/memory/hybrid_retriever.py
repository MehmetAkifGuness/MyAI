from collections.abc import Sequence

from boru.memory.contracts import (
    MemoryRetriever,
)
from boru.memory.models import (
    MemoryRecord,
)


class HybridMemoryRetriever:
    """
    Keyword ve semantic sıralamalarını
    reciprocal-rank fusion ile birleştirir.
    """

    def __init__(
        self,
        keyword_retriever: (
            MemoryRetriever
        ),
        semantic_retriever: (
            MemoryRetriever
        ),
        keyword_weight: float = 1.0,
        semantic_weight: float = 1.5,
        rank_constant: int = 60,
        candidate_multiplier: int = 4,
    ):
        if keyword_weight < 0.0:
            raise ValueError(
                (
                    "keyword_weight "
                    "negatif olamaz."
                )
            )

        if semantic_weight < 0.0:
            raise ValueError(
                (
                    "semantic_weight "
                    "negatif olamaz."
                )
            )

        if (
            keyword_weight == 0.0
            and semantic_weight == 0.0
        ):
            raise ValueError(
                (
                    "En az bir retrieval "
                    "ağırlığı pozitif olmalıdır."
                )
            )

        if rank_constant < 1:
            raise ValueError(
                (
                    "rank_constant "
                    "en az 1 olmalıdır."
                )
            )

        if candidate_multiplier < 1:
            raise ValueError(
                (
                    "candidate_multiplier "
                    "en az 1 olmalıdır."
                )
            )

        self._keyword_retriever = (
            keyword_retriever
        )

        self._semantic_retriever = (
            semantic_retriever
        )

        self._keyword_weight = (
            keyword_weight
        )

        self._semantic_weight = (
            semantic_weight
        )

        self._rank_constant = (
            rank_constant
        )

        self._candidate_multiplier = (
            candidate_multiplier
        )

    def retrieve(
        self,
        query: str,
        memories: Sequence[
            MemoryRecord
        ],
        limit: int,
    ) -> list[MemoryRecord]:
        if limit < 1:
            raise ValueError(
                "limit en az 1 olmalıdır."
            )

        if (
            not query.strip()
            or not memories
        ):
            return []

        candidate_limit = min(
            len(memories),
            max(
                limit,
                (
                    limit
                    * self._candidate_multiplier
                ),
            ),
        )

        keyword_results = (
            self._keyword_retriever
            .retrieve(
                query=query,
                memories=memories,
                limit=candidate_limit,
            )
        )

        semantic_results = (
            self._semantic_retriever
            .retrieve(
                query=query,
                memories=memories,
                limit=candidate_limit,
            )
        )

        scores: dict[
            str,
            float,
        ] = {}

        records: dict[
            str,
            MemoryRecord,
        ] = {}

        self._accumulate(
            keyword_results,
            self._keyword_weight,
            scores,
            records,
        )

        self._accumulate(
            semantic_results,
            self._semantic_weight,
            scores,
            records,
        )

        ranked = sorted(
            records.values(),
            key=lambda memory: (
                scores[
                    memory.memory_id
                ],
                memory.updated_at,
            ),
            reverse=True,
        )

        return ranked[:limit]

    def _accumulate(
        self,
        results: Sequence[
            MemoryRecord
        ],
        weight: float,
        scores: dict[
            str,
            float,
        ],
        records: dict[
            str,
            MemoryRecord,
        ],
    ) -> None:
        if weight <= 0.0:
            return

        for (
            rank,
            memory,
        ) in enumerate(
            results,
            start=1,
        ):
            records[
                memory.memory_id
            ] = memory

            scores[
                memory.memory_id
            ] = (
                scores.get(
                    memory.memory_id,
                    0.0,
                )
                + weight
                / (
                    self._rank_constant
                    + rank
                )
            )