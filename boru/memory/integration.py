from boru.memory.contracts import (
    MemoryIntentDetector,
    MemoryService,
)


class MemoryObserver:
    def __init__(
        self,
        memory_service: MemoryService,
    ):
        self._memory_service = (
            memory_service
        )

    def observe(
        self,
        user_message: str,
    ) -> None:
        self._memory_service.observe(
            user_message
        )


class MemoryContextProvider:
    """
    LLM context'ine uzun süreli hafıza
    eklenmesini yönetir.

    intent_detector verilmezse eski sürümlerle
    uyumluluk için mevcut davranışı korur.
    """

    def __init__(
        self,
        memory_service: MemoryService,
        intent_detector: (
            MemoryIntentDetector | None
        ) = None,
    ):
        self._memory_service = (
            memory_service
        )

        self._intent_detector = (
            intent_detector
        )

    def build_context(
        self,
        user_message: str,
    ) -> str:
        if (
            self._intent_detector
            is not None
            and not self._intent_detector
            .is_memory_relevant(
                user_message
            )
        ):
            return ""

        return (
            self._memory_service
            .build_context(
                user_message
            )
        )