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


class MemoryForgetTests(
    unittest.TestCase
):
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

    def test_parser_parses_targeted_forget_command(
        self,
    ) -> None:
        parser = (
            RuleBasedMemoryForgetParser()
        )

        request = parser.parse(
            (
                "Calculator API'nin test "
                "framework bilgisini unut."
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
            request.subject,
            "Calculator API",
        )

        self.assertEqual(
            request.relation,
            "test_framework",
        )

    def test_parser_parses_possessive_semantic_alias(
        self,
    ) -> None:
        parser = (
            RuleBasedMemoryForgetParser()
        )

        request = parser.parse(
            (
                "Hesap makinesi API'min test "
                "altyapısı bilgisini unut."
            )
        )

        self.assertIsNotNone(
            request
        )

        self.assertEqual(
            request.subject,
            "Hesap makinesi API",
        )

        self.assertEqual(
            request.relation,
            "test_framework",
        )

    def test_parser_parses_latest_and_all_commands(
        self,
    ) -> None:
        parser = (
            RuleBasedMemoryForgetParser()
        )

        latest = parser.parse(
            "En son kaydettiğin bilgiyi unut."
        )

        clear_all = parser.parse(
            "Her şeyi unut."
        )

        self.assertEqual(
            latest.mode,
            MemoryForgetMode.LATEST,
        )

        self.assertEqual(
            clear_all.mode,
            MemoryForgetMode.ALL,
        )

    def test_auto_memory_gate_rejects_forget_commands(
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
                    "Calculator API'nin test "
                    "framework bilgisini unut."
                )
            )
        )

        self.assertFalse(
            gate.should_evaluate(
                (
                    "Tüm uzun süreli hafızamı "
                    "silmeyi onaylıyorum."
                )
            )
        )

    def test_targeted_forget_removes_only_requested_relation(
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

            removed = (
                service.forget_structured(
                    subject="Calculator API",
                    relation="test_framework",
                )
            )

            records = (
                service.list_recent()
            )

            self.assertIsNotNone(
                removed
            )

            self.assertEqual(
                removed.relation,
                "test_framework",
            )

            self.assertEqual(
                len(records),
                1,
            )

            self.assertEqual(
                records[0].relation,
                "backend_framework",
            )

    def test_targeted_forget_uses_semantic_subject_identity(
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

            removed = (
                service.forget_structured(
                    subject="Hesap makinesi API",
                    relation="test_framework",
                )
            )

            self.assertIsNotNone(
                removed
            )

            self.assertEqual(
                service.list_recent(),
                [],
            )

    def test_forget_latest_removes_most_recent_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(
                Path(directory)
                / "memory.json"
            )

            calculator = service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )[0]

            auth = service.observe(
                (
                    "Bunu hatırla: "
                    "Auth API projem "
                    "unittest kullanıyor."
                )
            )[0]

            removed = (
                service.forget_latest()
            )

            self.assertEqual(
                removed.memory_id,
                auth.memory_id,
            )

            self.assertEqual(
                [
                    record.memory_id
                    for record
                    in service.list_recent()
                ],
                [
                    calculator.memory_id
                ],
            )

    def test_ambiguous_forget_does_not_delete_memory(
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
                "Bu bilgiyi hafızandan sil."
            )

            self.assertIn(
                "net değil",
                answer,
            )

            self.assertEqual(
                len(service.list_recent()),
                1,
            )

    def test_clear_all_requires_explicit_confirmation(
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

            first_answer = resolver.resolve(
                "Her şeyi unut."
            )

            self.assertIn(
                "onaylıyorum",
                first_answer.casefold(),
            )

            self.assertEqual(
                len(service.list_recent()),
                1,
            )

            second_answer = resolver.resolve(
                (
                    "Tüm uzun süreli hafızamı "
                    "silmeyi onaylıyorum."
                )
            )

            self.assertIn(
                "sildim",
                second_answer,
            )

            self.assertEqual(
                service.list_recent(),
                [],
            )

    def test_clear_all_confirmation_without_pending_request_is_safe(
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
                    "Tüm uzun süreli hafızamı "
                    "silmeyi onaylıyorum."
                )
            )

            self.assertIn(
                "bekleyen bir işlem yok",
                answer,
            )

            self.assertEqual(
                len(service.list_recent()),
                1,
            )

    def test_clear_all_can_be_cancelled(
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

            resolver.resolve(
                "Her şeyi unut."
            )

            answer = resolver.resolve(
                "İptal et."
            )

            self.assertIn(
                "iptal ettim",
                answer,
            )

            self.assertEqual(
                len(service.list_recent()),
                1,
            )

    def test_targeted_resolver_removes_memory_without_llm(
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
                    "Hesap makinesi API'min "
                    "test framework bilgisini "
                    "unut."
                )
            )

            self.assertIn(
                "Unuttum:",
                answer,
            )

            self.assertEqual(
                service.list_recent(),
                [],
            )


if __name__ == "__main__":
    unittest.main()