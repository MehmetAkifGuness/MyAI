import unittest

from boru.memory.models import (
    MemoryRecord,
)
from boru.memory.relevant_query_resolver import (
    RelevantMemoryQueryResolver,
)


class StubMemoryService:
    def __init__(
        self,
        memories: list[MemoryRecord],
    ):
        self._memories = memories

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        return list(
            self._memories[:limit]
        )


class GroundedUnknownMemoryTests(
    unittest.TestCase
):
    @staticmethod
    def _memory(
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

    def test_existing_memory_is_still_returned(
        self,
    ) -> None:
        resolver = (
            RelevantMemoryQueryResolver(
                StubMemoryService(
                    [
                        self._memory()
                    ]
                )
            )
        )

        answer = resolver.resolve(
            (
                "Calculator API projem "
                "ne kullanıyor?"
            )
        )

        self.assertEqual(
            answer,
            (
                "Hafızamdaki ilgili "
                "bilgiye göre: "
                "Calculator API projem "
                "artık unittest kullanıyor."
            ),
        )

    def test_unknown_project_question_is_grounded(
        self,
    ) -> None:
        resolver = (
            RelevantMemoryQueryResolver(
                StubMemoryService([])
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

    def test_unknown_service_question_is_grounded(
        self,
    ) -> None:
        resolver = (
            RelevantMemoryQueryResolver(
                StubMemoryService([])
            )
        )

        answer = resolver.resolve(
            (
                "Hesap makinesi servisimin "
                "test altyapısı neydi?"
            )
        )

        self.assertEqual(
            answer,
            (
                "Hafızamda bununla ilgili "
                "güvenilir bir bilgi yok."
            ),
        )

    def test_general_knowledge_question_still_reaches_llm(
        self,
    ) -> None:
        resolver = (
            RelevantMemoryQueryResolver(
                StubMemoryService([])
            )
        )

        answer = resolver.resolve(
            "Python nedir?"
        )

        self.assertIsNone(
            answer
        )


if __name__ == "__main__":
    unittest.main()