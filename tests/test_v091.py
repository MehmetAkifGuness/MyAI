import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.memory import (
    ConservativeMemoryDecisionGate,
    ExplicitMemoryExtractor,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LongTermMemoryService,
    RuleBasedMemoryForgetParser,
    RuleBasedMemoryForgetResolver,
    RuleBasedMemoryStructurer,
    SemanticSubjectMatcher,
    SubjectRelationConflictResolver,
)
from boru.memory.models import (
    MemoryForgetMode,
)


class SubjectEmbeddingProvider:
    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        return [
            self._vector(text)
            for text in texts
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


class SubjectLevelForgetTests(
    unittest.TestCase
):
    @staticmethod
    def _components():
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

        return matcher, resolver

    @classmethod
    def _service(
        cls,
        path: Path,
    ) -> LongTermMemoryService:
        matcher, conflict_resolver = (
            cls._components()
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
                conflict_resolver
            ),
            subject_matcher=matcher,
        )

    def test_parser_accepts_spaced_possessive_subject_command(
        self,
    ) -> None:
        parser = (
            RuleBasedMemoryForgetParser()
        )

        request = parser.parse(
            (
                "hesap makinesi api nin "
                "verilerini unut"
            )
        )

        self.assertIsNotNone(
            request
        )

        self.assertEqual(
            request.mode,
            MemoryForgetMode.SUBJECT,
        )

        self.assertEqual(
            request.subject,
            "hesap makinesi api",
        )

    def test_parser_accepts_related_everything_command(
        self,
    ) -> None:
        request = (
            RuleBasedMemoryForgetParser()
            .parse(
                (
                    "Calculator API ile ilgili "
                    "her şeyi unut."
                )
            )
        )

        self.assertIsNotNone(
            request
        )

        self.assertEqual(
            request.mode,
            MemoryForgetMode.SUBJECT,
        )

        self.assertEqual(
            request.subject,
            "Calculator API",
        )

    def test_relation_specific_command_still_has_priority(
        self,
    ) -> None:
        request = (
            RuleBasedMemoryForgetParser()
            .parse(
                (
                    "Calculator API'nin test "
                    "framework bilgisini unut."
                )
            )
        )

        self.assertIsNotNone(
            request
        )

        self.assertEqual(
            request.mode,
            MemoryForgetMode.TARGETED,
        )

        self.assertEqual(
            request.relation,
            "test_framework",
        )

    def test_global_clear_command_is_not_subject_delete(
        self,
    ) -> None:
        request = (
            RuleBasedMemoryForgetParser()
            .parse(
                "Her şeyi unut."
            )
        )

        self.assertIsNotNone(
            request
        )

        self.assertEqual(
            request.mode,
            MemoryForgetMode.ALL,
        )

    def test_auto_memory_gate_rejects_subject_forget_command(
        self,
    ) -> None:
        parser = (
            RuleBasedMemoryForgetParser()
        )

        gate = (
            ConservativeMemoryDecisionGate(
                forget_parser=parser
            )
        )

        self.assertFalse(
            gate.should_evaluate(
                (
                    "Hesap makinesi API hakkında "
                    "bildiklerini unut."
                )
            )
        )

    def test_forget_subject_removes_all_relations_and_preserves_other_subjects(
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

            service.observe(
                (
                    "Bunu hatırla: "
                    "Auth API projem "
                    "unittest kullanıyor."
                )
            )

            removed = service.forget_subject(
                "Hesap makinesi API"
            )

            remaining = (
                service.list_recent()
            )

            self.assertEqual(
                len(removed),
                2,
            )

            self.assertEqual(
                {
                    memory.relation
                    for memory in removed
                },
                {
                    "test_framework",
                    "backend_framework",
                },
            )

            self.assertEqual(
                len(remaining),
                1,
            )

            self.assertEqual(
                remaining[0].subject,
                "Auth API",
            )

    def test_subject_resolver_handles_natural_user_command(
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

            resolver = (
                RuleBasedMemoryForgetResolver(
                    memory_service=service,
                    parser=(
                        RuleBasedMemoryForgetParser()
                    ),
                )
            )

            answer = resolver.resolve(
                (
                    "hesap makinesi api nin "
                    "verilerini unut"
                )
            )

            self.assertIn(
                "2 uzun süreli hafıza",
                answer,
            )

            self.assertEqual(
                service.list_recent(),
                [],
            )

    def test_unknown_subject_does_not_delete_existing_memory(
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
                    "pytest kullanıyor."
                )
            )

            resolver = (
                RuleBasedMemoryForgetResolver(
                    memory_service=service,
                    parser=(
                        RuleBasedMemoryForgetParser()
                    ),
                )
            )

            answer = resolver.resolve(
                (
                    "Auth API hakkında "
                    "bildiklerini unut."
                )
            )

            self.assertIn(
                "kayıt bulamadım",
                answer,
            )

            self.assertEqual(
                len(service.list_recent()),
                1,
            )


if __name__ == "__main__":
    unittest.main()