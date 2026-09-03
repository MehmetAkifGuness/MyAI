import unittest

from boru.memory.integration import (
    MemoryContextProvider,
)
from boru.memory.intent import (
    RuleBasedMemoryIntentDetector,
)
from boru.memory.models import (
    MemoryRecord,
)
from boru.memory.relevant_query_resolver import (
    RelevantMemoryQueryResolver,
)


class RecordingMemoryService:
    def __init__(
        self,
        search_results: (
            list[MemoryRecord] | None
        ) = None,
        context: str = "MEMORY CONTEXT",
    ):
        self.search_results = (
            search_results
            if search_results is not None
            else []
        )

        self.context = context
        self.search_calls: list[str] = []
        self.context_calls: list[str] = []

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        self.search_calls.append(
            query
        )

        return list(
            self.search_results[:limit]
        )

    def build_context(
        self,
        query: str,
    ) -> str:
        self.context_calls.append(
            query
        )

        return self.context


class MemoryIntentIsolationTests(
    unittest.TestCase
):
    @staticmethod
    def _calculator_memory(
    ) -> MemoryRecord:
        return MemoryRecord(
            memory_id="calculator",
            content=(
                "Calculator API projem "
                "artık unittest kullanıyor."
            ),
            created_at=(
                "2026-09-03"
                "T10:00:00+00:00"
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
            subject="Calculator API",
            relation="test_framework",
            value="unittest",
        )

    def test_general_question_is_not_memory_intent(
        self,
    ) -> None:
        detector = (
            RuleBasedMemoryIntentDetector()
        )

        self.assertFalse(
            detector.is_memory_relevant(
                "Java nedir?"
            )
        )

    def test_project_question_is_memory_intent(
        self,
    ) -> None:
        detector = (
            RuleBasedMemoryIntentDetector()
        )

        self.assertTrue(
            detector.is_memory_relevant(
                (
                    "Calculator API projem "
                    "ne kullanıyor?"
                )
            )
        )

    def test_general_question_does_not_search_memory(
        self,
    ) -> None:
        service = RecordingMemoryService(
            search_results=[
                self._calculator_memory()
            ]
        )

        resolver = (
            RelevantMemoryQueryResolver(
                service,
                intent_detector=(
                    RuleBasedMemoryIntentDetector()
                ),
            )
        )

        answer = resolver.resolve(
            "Java nedir?"
        )

        self.assertIsNone(
            answer
        )

        self.assertEqual(
            service.search_calls,
            [],
        )

    def test_general_message_does_not_receive_memory_context(
        self,
    ) -> None:
        service = (
            RecordingMemoryService()
        )

        provider = (
            MemoryContextProvider(
                service,
                intent_detector=(
                    RuleBasedMemoryIntentDetector()
                ),
            )
        )

        context = provider.build_context(
            "java ned"
        )

        self.assertEqual(
            context,
            "",
        )

        self.assertEqual(
            service.context_calls,
            [],
        )

    def test_project_message_can_receive_memory_context(
        self,
    ) -> None:
        service = (
            RecordingMemoryService()
        )

        provider = (
            MemoryContextProvider(
                service,
                intent_detector=(
                    RuleBasedMemoryIntentDetector()
                ),
            )
        )

        message = (
            "Calculator API projemde "
            "bir değişiklik yapacağım."
        )

        context = provider.build_context(
            message
        )

        self.assertEqual(
            context,
            "MEMORY CONTEXT",
        )

        self.assertEqual(
            service.context_calls,
            [
                message
            ],
        )

    def test_unknown_personal_project_question_stays_grounded(
        self,
    ) -> None:
        service = (
            RecordingMemoryService()
        )

        resolver = (
            RelevantMemoryQueryResolver(
                service,
                intent_detector=(
                    RuleBasedMemoryIntentDetector()
                ),
            )
        )

        answer = resolver.resolve(
            (
                "Flutter uygulamamda "
                "state management olarak "
                "ne kullanıyorum?"
            )
        )

        self.assertEqual(
            answer,
            (
                "Hafızamda bununla ilgili "
                "güvenilir bir bilgi yok."
            ),
        )

        self.assertEqual(
            len(service.search_calls),
            1,
        )


if __name__ == "__main__":
    unittest.main()