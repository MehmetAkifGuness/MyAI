import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.memory import (
    ExplicitMemoryExtractor,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LongTermMemoryService,
    RuleBasedMemoryStructurer,
    SemanticSubjectMatcher,
    SubjectRelationConflictResolver,
)
from boru.memory.models import (
    MemoryRecord,
    StructuredMemoryFact,
)


class SubjectEmbeddingProvider:
    def __init__(
        self,
    ):
        self.calls: list[
            list[str]
        ] = []

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        batch = list(
            texts
        )

        self.calls.append(
            batch
        )

        return [
            self._vector(text)
            for text in batch
        ]

    @staticmethod
    def _vector(
        text: str,
    ) -> list[float]:
        folded = text.casefold()

        if "auth api" in folded:
            return [
                0.0,
                1.0,
                0.0,
            ]

        if (
            "calculator api" in folded
            or "hesap makinesi api" in folded
            or "calculator" in folded
        ):
            return [
                1.0,
                0.0,
                0.0,
            ]

        return [
            0.0,
            0.0,
            1.0,
        ]


class FailingEmbeddingProvider:
    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        raise RuntimeError(
            "embedding unavailable"
        )


class SemanticMemoryIdentityTests(
    unittest.TestCase
):
    @staticmethod
    def _record(
        memory_id: str,
        subject: str,
        relation: str,
        value: str,
    ) -> MemoryRecord:
        return MemoryRecord(
            memory_id=memory_id,
            content=(
                f"{subject} projem "
                f"{value} kullanıyor."
            ),
            created_at=(
                "2026-09-03"
                "T10:00:00+00:00"
            ),
            updated_at=(
                "2026-09-03"
                "T10:00:00+00:00"
            ),
            subject=subject,
            relation=relation,
            value=value,
        )

    @staticmethod
    def _service(
        path: Path,
    ) -> LongTermMemoryService:
        matcher = (
            SemanticSubjectMatcher(
                embedding_provider=(
                    SubjectEmbeddingProvider()
                ),
                minimum_similarity=0.8,
            )
        )

        return LongTermMemoryService(
            repository=(
                JsonMemoryRepository(
                    path
                )
            ),
            extractor=(
                ExplicitMemoryExtractor()
            ),
            retriever=(
                KeywordMemoryRetriever()
            ),
            structurer=(
                RuleBasedMemoryStructurer()
            ),
            conflict_resolver=(
                SubjectRelationConflictResolver(
                    subject_matcher=matcher
                )
            ),
        )

    def test_structurer_parses_named_api_possessive_form(
        self,
    ) -> None:
        fact = (
            RuleBasedMemoryStructurer()
            .structure(
                (
                    "Hesap makinesi API'm "
                    "artık pytest kullanıyor."
                )
            )
        )

        self.assertIsNotNone(
            fact
        )

        self.assertEqual(
            fact.subject,
            "Hesap makinesi API",
        )

        self.assertEqual(
            fact.relation,
            "test_framework",
        )

        self.assertEqual(
            fact.value,
            "pytest",
        )

    def test_structurer_parses_service_test_paraphrase(
        self,
    ) -> None:
        fact = (
            RuleBasedMemoryStructurer()
            .structure(
                (
                    "Calculator servisimin "
                    "testleri unittest ile "
                    "çalışıyor."
                )
            )
        )

        self.assertIsNotNone(
            fact
        )

        self.assertEqual(
            fact.subject,
            "Calculator",
        )

        self.assertEqual(
            fact.relation,
            "test_framework",
        )

        self.assertEqual(
            fact.value,
            "unittest",
        )

    def test_semantic_matcher_matches_translated_subject(
        self,
    ) -> None:
        matcher = (
            SemanticSubjectMatcher(
                embedding_provider=(
                    SubjectEmbeddingProvider()
                ),
                minimum_similarity=0.8,
            )
        )

        self.assertTrue(
            matcher.is_same_subject(
                "Calculator API",
                "Hesap makinesi API",
            )
        )

    def test_semantic_matcher_rejects_different_subject(
        self,
    ) -> None:
        matcher = (
            SemanticSubjectMatcher(
                embedding_provider=(
                    SubjectEmbeddingProvider()
                ),
                minimum_similarity=0.8,
            )
        )

        self.assertFalse(
            matcher.is_same_subject(
                "Calculator API",
                "Auth API",
            )
        )

    def test_semantic_matcher_fails_closed_when_embedding_fails(
        self,
    ) -> None:
        matcher = (
            SemanticSubjectMatcher(
                embedding_provider=(
                    FailingEmbeddingProvider()
                ),
                minimum_similarity=0.8,
            )
        )

        self.assertFalse(
            matcher.is_same_subject(
                "Calculator API",
                "Hesap makinesi API",
            )
        )

    def test_conflict_resolver_uses_semantic_subject_identity(
        self,
    ) -> None:
        matcher = (
            SemanticSubjectMatcher(
                embedding_provider=(
                    SubjectEmbeddingProvider()
                ),
                minimum_similarity=0.8,
            )
        )

        resolver = (
            SubjectRelationConflictResolver(
                subject_matcher=matcher
            )
        )

        existing = self._record(
            memory_id="calculator",
            subject="Calculator API",
            relation="test_framework",
            value="unittest",
        )

        found = resolver.find_existing(
            fact=StructuredMemoryFact(
                subject="Hesap makinesi API",
                relation="test_framework",
                value="pytest",
            ),
            memories=[
                existing
            ],
        )

        self.assertEqual(
            found,
            existing,
        )

    def test_semantic_alias_update_keeps_single_record_and_canonical_subject(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(
                Path(directory)
                / "memory.json"
            )

            first = service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "unittest kullanıyor."
                )
            )[0]

            updated = service.observe(
                (
                    "Bunu hatırla: "
                    "Hesap makinesi API'm "
                    "artık pytest kullanıyor."
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
                updated.subject,
                "Calculator API",
            )

            self.assertEqual(
                updated.relation,
                "test_framework",
            )

            self.assertEqual(
                updated.value,
                "pytest",
            )

    def test_semantic_duplicate_same_value_is_not_added_twice(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(
                Path(directory)
                / "memory.json"
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "unittest kullanıyor."
                )
            )

            changed = service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator servisimin "
                    "testleri unittest ile "
                    "çalışıyor."
                )
            )

            self.assertEqual(
                changed,
                [],
            )

            self.assertEqual(
                len(service.list_recent()),
                1,
            )

    def test_different_semantic_subject_is_added_separately(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(
                Path(directory)
                / "memory.json"
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "unittest kullanıyor."
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Auth API projem "
                    "pytest kullanıyor."
                )
            )

            records = (
                service.list_recent()
            )

            self.assertEqual(
                len(records),
                2,
            )

            self.assertEqual(
                {
                    record.subject
                    for record in records
                },
                {
                    "Calculator API",
                    "Auth API",
                },
            )


if __name__ == "__main__":
    unittest.main()