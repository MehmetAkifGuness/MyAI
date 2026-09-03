import json
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.memory import (
    ExplicitMemoryExtractor,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LLMMemoryDecisionEngine,
    LongTermMemoryService,
    RelevantMemoryQueryResolver,
    RuleBasedMemoryStructurer,
    SubjectRelationConflictResolver,
)
from boru.models import ChatMessage


class RecordingChatModel:
    def __init__(
        self,
        response: str,
    ):
        self.response = response

        self.calls: list[
            list[ChatMessage]
        ] = []

    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        self.calls.append(
            list(messages)
        )

        return self.response


class StructuredMemoryTests(
    unittest.TestCase
):
    @staticmethod
    def _create_service(
        path: Path,
    ) -> LongTermMemoryService:
        return LongTermMemoryService(
            repository=JsonMemoryRepository(
                path
            ),
            extractor=ExplicitMemoryExtractor(),
            retriever=KeywordMemoryRetriever(),
            structurer=RuleBasedMemoryStructurer(),
            conflict_resolver=(
                SubjectRelationConflictResolver()
            ),
        )

    def test_legacy_record_loads_with_created_at_as_updated_at(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            path.write_text(
                json.dumps(
                    [
                        {
                            "memory_id": "legacy-1",
                            "content": (
                                "Calculator API projem "
                                "pytest kullanıyor."
                            ),
                            "created_at": (
                                "2026-09-03"
                                "T10:00:00+00:00"
                            ),
                        }
                    ]
                ),
                encoding="utf-8",
            )

            repository = (
                JsonMemoryRepository(
                    path
                )
            )

            records = (
                repository.load_all()
            )

            self.assertEqual(
                records[0].updated_at,
                records[0].created_at,
            )

    def test_structurer_detects_test_framework(
        self,
    ) -> None:
        structurer = (
            RuleBasedMemoryStructurer()
        )

        fact = structurer.structure(
            (
                "Calculator API projem "
                "pytest kullanıyor."
            )
        )

        self.assertIsNotNone(
            fact
        )

        self.assertEqual(
            fact.subject,
            "Calculator API",
        )

        self.assertEqual(
            fact.relation,
            "test_framework",
        )

        self.assertEqual(
            fact.value,
            "pytest",
        )

    def test_explicit_memory_is_saved_structured(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = (
                self._create_service(
                    (
                        Path(directory)
                        / "memory.json"
                    )
                )
            )

            saved = service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            self.assertEqual(
                len(saved),
                1,
            )

            self.assertEqual(
                saved[0].subject,
                "Calculator API",
            )

            self.assertEqual(
                saved[0].relation,
                "test_framework",
            )

            self.assertEqual(
                saved[0].value,
                "pytest",
            )

    def test_conflicting_value_updates_existing_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = (
                self._create_service(
                    (
                        Path(directory)
                        / "memory.json"
                    )
                )
            )

            first = service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )[0]

            updated = service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "artık unittest "
                    "kullanıyor."
                )
            )[0]

            records = (
                service.list_recent()
            )

            self.assertEqual(
                len(records),
                1,
            )

            self.assertEqual(
                updated.memory_id,
                first.memory_id,
            )

            self.assertEqual(
                updated.created_at,
                first.created_at,
            )

            self.assertEqual(
                updated.value,
                "unittest",
            )

            self.assertIn(
                "unittest",
                updated.content,
            )

    def test_different_relation_does_not_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = (
                self._create_service(
                    (
                        Path(directory)
                        / "memory.json"
                    )
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "FastAPI kullanıyor."
                )
            )

            records = (
                service.list_recent()
            )

            relations = {
                record.relation
                for record in records
            }

            self.assertEqual(
                len(records),
                2,
            )

            self.assertEqual(
                relations,
                {
                    "test_framework",
                    "backend_framework",
                },
            )

    def test_different_subject_does_not_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = (
                self._create_service(
                    (
                        Path(directory)
                        / "memory.json"
                    )
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Auth API projem "
                    "unittest kullanıyor."
                )
            )

            records = (
                service.list_recent()
            )

            subjects = {
                record.subject
                for record in records
            }

            self.assertEqual(
                len(records),
                2,
            )

            self.assertEqual(
                subjects,
                {
                    "Calculator API",
                    "Auth API",
                },
            )

    def test_legacy_record_is_enriched_and_then_updated(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            path.write_text(
                json.dumps(
                    [
                        {
                            "memory_id": "legacy-1",
                            "content": (
                                "Calculator API projem "
                                "pytest kullanıyor."
                            ),
                            "created_at": (
                                "2026-09-03"
                                "T10:00:00+00:00"
                            ),
                        }
                    ]
                ),
                encoding="utf-8",
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "artık unittest "
                    "kullanıyor."
                )
            )

            records = (
                service.list_recent()
            )

            self.assertEqual(
                len(records),
                1,
            )

            self.assertEqual(
                records[0].memory_id,
                "legacy-1",
            )

            self.assertEqual(
                records[0].relation,
                "test_framework",
            )

            self.assertEqual(
                records[0].value,
                "unittest",
            )

    def test_grounded_query_returns_updated_value_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = (
                self._create_service(
                    (
                        Path(directory)
                        / "memory.json"
                    )
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "artık unittest "
                    "kullanıyor."
                )
            )

            resolver = (
                RelevantMemoryQueryResolver(
                    service
                )
            )

            answer = resolver.resolve(
                (
                    "Calculator API projem "
                    "ne kullanıyor?"
                )
            )

            self.assertIn(
                "unittest",
                answer,
            )

            self.assertNotIn(
                "pytest",
                answer,
            )

    def test_llm_decision_can_return_structured_fact(
        self,
    ) -> None:
        model = RecordingChatModel(
            (
                '{"save": true, '
                '"content": '
                '"Calculator API projem '
                'unittest kullanıyor.", '
                '"subject": '
                '"Calculator API", '
                '"relation": '
                '"test_framework", '
                '"value": "unittest", '
                '"reason": '
                '"Kalıcı proje bilgisi."}'
            )
        )

        decision = (
            LLMMemoryDecisionEngine(
                model
            )
            .decide(
                (
                    "Calculator API projem "
                    "unittest kullanıyor."
                )
            )
        )

        self.assertTrue(
            decision.should_save
        )

        self.assertIsNotNone(
            decision.fact
        )

        self.assertEqual(
            decision.fact.relation,
            "test_framework",
        )

        self.assertEqual(
            decision.fact.value,
            "unittest",
        )


if __name__ == "__main__":
    unittest.main()