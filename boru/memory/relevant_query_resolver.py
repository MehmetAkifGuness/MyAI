import re

from boru.memory.contracts import (
    MemoryIntentDetector,
    MemoryService,
)
from boru.memory.intent import (
    RuleBasedMemoryIntentDetector,
)
from boru.memory.models import (
    MemoryRecord,
)


class RelevantMemoryQueryResolver:
    """
    Kullanıcının kendi kalıcı bilgileriyle
    ilgili soruları LLM'e bırakmadan
    hafızadan güvenilir biçimde yanıtlar.

    Genel bilgi sorularında hafıza araması
    yapılmaz. Böylece semantic false-positive
    sonuçların doğrudan cevap haline gelmesi
    engellenir.
    """

    _QUESTION_WORD_PATTERN = re.compile(
        (
            r"\b("
            r"ne|nedir|neydi|"
            r"hangi|hangisi|"
            r"kim|kaç|nasıl|"
            r"neden|nerede|"
            r"ne\s+zaman"
            r")\b"
        ),
        re.IGNORECASE,
    )

    _UNKNOWN_MEMORY_RESPONSE = (
        "Hafızamda bununla ilgili "
        "güvenilir bir bilgi yok."
    )

    def __init__(
        self,
        memory_service: MemoryService,
        result_limit: int = 3,
        intent_detector: (
            MemoryIntentDetector | None
        ) = None,
    ):
        if result_limit < 1:
            raise ValueError(
                (
                    "result_limit "
                    "en az 1 olmalıdır."
                )
            )

        self._memory_service = (
            memory_service
        )

        self._result_limit = (
            result_limit
        )

        self._intent_detector = (
            intent_detector
            or RuleBasedMemoryIntentDetector()
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

        if not self._looks_like_question(
            normalized
        ):
            return None

        if not (
            self._intent_detector
            .is_memory_relevant(
                normalized
            )
        ):
            return None

        memories = (
            self._memory_service.search(
                query=normalized,
                limit=self._result_limit,
            )
        )

        if memories:
            return self._build_answer(
                memories
            )

        return (
            self._UNKNOWN_MEMORY_RESPONSE
        )

    @classmethod
    def _looks_like_question(
        cls,
        value: str,
    ) -> bool:
        if "?" in value:
            return True

        return (
            cls._QUESTION_WORD_PATTERN
            .search(value)
            is not None
        )

    @staticmethod
    def _build_answer(
        memories: list[MemoryRecord],
    ) -> str:
        if len(memories) == 1:
            return (
                "Hafızamdaki ilgili "
                "bilgiye göre: "
                f"{memories[0].content}"
            )

        lines = [
            f"- {memory.content}"
            for memory
            in memories
        ]

        return (
            "Hafızamdaki ilgili "
            "bilgilere göre:\n"
            + "\n".join(lines)
        )

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value.strip().split()
        )