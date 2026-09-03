import re

from boru.memory.contracts import (
    MemoryService,
)


class RuleBasedMemoryQueryResolver:
    """
    Hafıza listesini isteyen açık sorguları
    LLM'e bırakmadan yanıtlar.
    """

    _LIST_PATTERNS = (
        re.compile(
            (
                r"^hafızanda\s+"
                r"ne\s+var$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^uzun\s+süreli\s+"
                r"hafızanda\s+"
                r"ne\s+var$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^neleri\s+"
                r"hatırlıyorsun$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^ne\s+"
                r"hatırlıyorsun$"
            ),
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        memory_service: MemoryService,
        list_limit: int = 20,
    ):
        if list_limit < 1:
            raise ValueError(
                (
                    "list_limit "
                    "en az 1 olmalıdır."
                )
            )

        self._memory_service = (
            memory_service
        )

        self._list_limit = (
            list_limit
        )

    def resolve(
        self,
        user_message: str,
    ) -> str | None:
        normalized = self._normalize(
            user_message
        )

        if not normalized:
            return None

        if not any(
            pattern.fullmatch(
                normalized
            )
            for pattern
            in self._LIST_PATTERNS
        ):
            return None

        memories = (
            self._memory_service
            .list_recent(
                self._list_limit
            )
        )

        if not memories:
            return (
                "Uzun süreli hafızamda "
                "kayıtlı bilgi yok."
            )

        return (
            "Uzun süreli hafızamda "
            "şunlar var:\n"
            + "\n".join(
                (
                    f"- {memory.content}"
                    for memory
                    in memories
                )
            )
        )

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        cleaned = (
            value
            .strip()
            .rstrip(".!?")
            .strip()
        )

        return " ".join(
            cleaned.split()
        )