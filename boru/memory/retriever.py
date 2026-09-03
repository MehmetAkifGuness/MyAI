import re
from collections.abc import (
    Sequence,
)

from boru.memory.models import (
    MemoryRecord,
)


class KeywordMemoryRetriever:
    """
    Yapılandırılmış alanları da kullanan
    deterministik hafıza getirici.
    """

    _TOKEN_PATTERN = re.compile(
        r"\w+",
        re.UNICODE,
    )

    _STOP_WORDS = {
        "acaba",
        "ama",
        "ben",
        "benim",
        "bir",
        "bu",
        "da",
        "de",
        "daha",
        "diye",
        "hangi",
        "ile",
        "için",
        "mi",
        "mı",
        "mu",
        "mü",
        "ne",
        "neydi",
        "nedir",
        "o",
        "olarak",
        "sen",
        "şey",
        "ve",
        "ya",
    }

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
                (
                    "limit en az "
                    "1 olmalıdır."
                )
            )

        query_tokens = (
            self._tokens(
                query
            )
        )

        if not query_tokens:
            return []

        scored: list[
            tuple[
                float,
                MemoryRecord,
            ]
        ] = []

        for memory in memories:
            searchable_text = (
                self._searchable_text(
                    memory
                )
            )

            memory_tokens = (
                self._tokens(
                    searchable_text
                )
            )

            overlap = (
                query_tokens
                .intersection(
                    memory_tokens
                )
            )

            if not overlap:
                continue

            base_score = (
                len(overlap)
                / len(query_tokens)
            )

            subject_bonus = (
                self._subject_bonus(
                    query_tokens,
                    memory,
                )
            )

            score = (
                base_score
                + subject_bonus
            )

            scored.append(
                (
                    score,
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

    def _searchable_text(
        self,
        memory: MemoryRecord,
    ) -> str:
        parts = [
            memory.content
        ]

        if memory.subject:
            parts.append(
                memory.subject
            )

        if memory.relation:
            parts.append(
                memory.relation.replace(
                    "_",
                    " ",
                )
            )

        if memory.value:
            parts.append(
                memory.value
            )

        return " ".join(
            parts
        )

    def _subject_bonus(
        self,
        query_tokens: set[str],
        memory: MemoryRecord,
    ) -> float:
        if not memory.subject:
            return 0.0

        subject_tokens = (
            self._tokens(
                memory.subject
            )
        )

        if not subject_tokens:
            return 0.0

        overlap = (
            query_tokens
            .intersection(
                subject_tokens
            )
        )

        return (
            0.5
            * (
                len(overlap)
                / len(subject_tokens)
            )
        )

    def _tokens(
        self,
        value: str,
    ) -> set[str]:
        tokens = {
            token.casefold()
            for token
            in (
                self._TOKEN_PATTERN
                .findall(value)
            )
            if len(token) > 1
        }

        return tokens.difference(
            self._STOP_WORDS
        )