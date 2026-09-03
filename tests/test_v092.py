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


class CoreAwareEmbeddingProvider:
    """
    Test provider'ı yalnızca matcher'ın gönderdiği
    identity core metnini değerlendirir.
    """

    def __init__(
        self,
    ):
        self.calls: list[list[str]] = []

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        batch = list(texts)
        self.calls.append(batch)

        return [
            self._vector(text)
            for text in batch
        ]

    @staticmethod
    def _vector(
        text: str,
    ) -> list[float]:
        folded = text.casefold().strip()

        if (
            "calculator" in folded
            or "hesap makinesi" in folded
        ):
            return [
                1.0,
                0.0,
                0.0,
            ]

        if "auth" in folded:
            return [
                0.0,
                1.0,
                0.0,
            ]

        return [
            0.0,
            0.0,
            1.0,
        ]


class MisleadingGenericEmbeddingProvider:
    """
    Eski matcher gibi tüm teknik subject metnini
    karşılaştırmak yanlış olsaydı API kelimesi yüksek
    benzerlik üretebilirdi. Yeni matcher generic suffix'i
    çıkardığı için bu provider Calculator/Auth ayrımını
    yine güvenli biçimde yapabilmelidir.
    """

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        result = []

        for text in texts:
            folded = text.casefold().strip()

            if folded == "calculator":
                result.append([
                    1.0,
                    0.0,
                    0.0,
                ])

            elif folded in {
                "hesap makinesi",
                "hesap makinesi api",
            }:
                result.append([
                    1.0,
                    0.0,
                    0.0,
                ])

            elif folded == "auth":
                result.append([
                    0.0,
                    1.0,
                    0.0,
                ])

            else:
                result.append([
                    0.9,
                    0.9,
                    0.0,
                ])

        return result


class SafeSemanticSubjectIdentityTests(
    unittest.TestCase
):
    @staticmethod
    def _matcher():
        return SemanticSubjectMatcher(
            embedding_provider=(
                CoreAwareEmbeddingProvider()
            ),
            minimum_similarity=0.8,
        )

    @classmethod
    def _service(
        cls,
        path: Path,
    ) -> LongTermMemoryService:
        matcher = cls._matcher()

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
            subject_matcher=matcher,
        )

    def test_identity_core_removes_generic_api_suffix(
        self,
    ) -> None:
        matcher = self._matcher()

        self.assertEqual(
            matcher._identity_core(
                "Calculator API"
            ),
            "Calculator",
        )

        self.assertEqual(
            matcher._identity_core(
                "Hesap makinesi API"
            ),
            "Hesap makinesi",
        )

    def test_distinct_single_token_names_do_not_use_semantic_merge(
        self,
    ) -> None:
        provider = (
            CoreAwareEmbeddingProvider()
        )

        matcher = SemanticSubjectMatcher(
            embedding_provider=provider,
            minimum_similarity=0.0,
        )

        self.assertFalse(
            matcher.is_same_subject(
                "Calculator API",
                "Auth API",
            )
        )

        self.assertEqual(
            provider.calls,
            [],
        )

    def test_translated_multiword_alias_still_matches(
        self,
    ) -> None:
        matcher = self._matcher()

        self.assertTrue(
            matcher.is_same_subject(
                "Calculator API",
                "Hesap makinesi API",
            )
        )

    def test_generic_api_word_cannot_force_false_identity(
        self,
    ) -> None:
        matcher = SemanticSubjectMatcher(
            embedding_provider=(
                MisleadingGenericEmbeddingProvider()
            ),
            minimum_similarity=0.8,
        )

        self.assertFalse(
            matcher.is_same_subject(
                "Calculator API",
                "Auth API",
            )
        )

    def test_real_user_scenario_keeps_auth_and_calculator_separate(
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

            records = (
                service.list_recent()
            )

            self.assertEqual(
                len(records),
                3,
            )

            facts = {
                (
                    record.subject,
                    record.relation,
                    record.value,
                )
                for record in records
            }

            self.assertEqual(
                facts,
                {
                    (
                        "Calculator API",
                        "test_framework",
                        "pytest",
                    ),
                    (
                        "Calculator API",
                        "backend_framework",
                        "FastAPI",
                    ),
                    (
                        "Auth API",
                        "test_framework",
                        "unittest",
                    ),
                },
            )

    def test_subject_forget_removes_calculator_only(
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

            removed = (
                service.forget_subject(
                    "Hesap makinesi API"
                )
            )

            self.assertEqual(
                len(removed),
                2,
            )

            remaining = (
                service.list_recent()
            )

            self.assertEqual(
                len(remaining),
                1,
            )

            self.assertEqual(
                remaining[0].subject,
                "Auth API",
            )

            self.assertEqual(
                remaining[0].value,
                "unittest",
            )


if __name__ == "__main__":
    unittest.main()