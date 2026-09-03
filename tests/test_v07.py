import unittest
from collections.abc import (
    Sequence,
)

from boru.memory import (
    HybridMemoryRetriever,
    KeywordMemoryRetriever,
    OllamaEmbeddingProvider,
    SemanticMemoryRetriever,
)
from boru.memory.models import (
    MemoryRecord,
)


class RuleEmbeddingProvider:
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
        folded = (
            text.casefold()
        )

        if (
            "hesap makinesi" in folded
            or "calculator api" in folded
            or "unittest" in folded
        ):
            return [
                1.0,
                0.0,
                0.0,
            ]

        if (
            "flutter" in folded
            or "riverpod" in folded
        ):
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


class FailingEmbeddingProvider:
    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        raise RuntimeError(
            "embedding unavailable"
        )


class SemanticMemoryTests(
    unittest.TestCase
):
    @staticmethod
    def _memory(
        memory_id: str,
        content: str,
        updated_at: str,
        subject: str | None = None,
        relation: str | None = None,
        value: str | None = None,
    ) -> MemoryRecord:
        return MemoryRecord(
            memory_id=memory_id,
            content=content,
            created_at=(
                "2026-09-03"
                "T10:00:00+00:00"
            ),
            updated_at=updated_at,
            subject=subject,
            relation=relation,
            value=value,
        )

    def test_semantic_retriever_matches_different_wording(
        self,
    ) -> None:
        provider = (
            RuleEmbeddingProvider()
        )

        retriever = (
            SemanticMemoryRetriever(
                embedding_provider=provider,
                minimum_similarity=0.8,
            )
        )

        calculator = self._memory(
            memory_id="calculator",
            content=(
                "Calculator API projem "
                "artık unittest kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
            subject="Calculator API",
            relation="test_framework",
            value="unittest",
        )

        flutter = self._memory(
            memory_id="flutter",
            content=(
                "Flutter projem "
                "Riverpod kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
            subject="Flutter",
            relation="state_management",
            value="Riverpod",
        )

        result = retriever.retrieve(
            query=(
                "Hesap makinesi servisimin "
                "test altyapısı neydi?"
            ),
            memories=[
                calculator,
                flutter,
            ],
            limit=2,
        )

        self.assertEqual(
            result,
            [
                calculator
            ],
        )

    def test_semantic_retriever_uses_embedding_cache(
        self,
    ) -> None:
        provider = (
            RuleEmbeddingProvider()
        )

        retriever = (
            SemanticMemoryRetriever(
                embedding_provider=provider,
                minimum_similarity=0.8,
            )
        )

        memory = self._memory(
            memory_id="calculator",
            content=(
                "Calculator API projem "
                "unittest kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
        )

        retriever.retrieve(
            query=(
                "Hesap makinesi "
                "test altyapısı"
            ),
            memories=[
                memory
            ],
            limit=1,
        )

        retriever.retrieve(
            query=(
                "Hesap makinesi "
                "test sistemi"
            ),
            memories=[
                memory
            ],
            limit=1,
        )

        self.assertEqual(
            len(provider.calls),
            2,
        )

        self.assertEqual(
            len(provider.calls[0]),
            2,
        )

        self.assertEqual(
            len(provider.calls[1]),
            1,
        )

    def test_updated_memory_is_reembedded(
        self,
    ) -> None:
        provider = (
            RuleEmbeddingProvider()
        )

        retriever = (
            SemanticMemoryRetriever(
                embedding_provider=provider,
                minimum_similarity=0.8,
            )
        )

        original = self._memory(
            memory_id="calculator",
            content=(
                "Calculator API projem "
                "pytest kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
        )

        updated = self._memory(
            memory_id="calculator",
            content=(
                "Calculator API projem "
                "unittest kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T12:00:00+00:00"
            ),
        )

        retriever.retrieve(
            query=(
                "Hesap makinesi "
                "test altyapısı"
            ),
            memories=[
                original
            ],
            limit=1,
        )

        retriever.retrieve(
            query=(
                "Hesap makinesi "
                "test altyapısı"
            ),
            memories=[
                updated
            ],
            limit=1,
        )

        self.assertEqual(
            len(provider.calls),
            2,
        )

        self.assertEqual(
            len(provider.calls[1]),
            2,
        )

    def test_hybrid_retriever_falls_back_to_keyword_when_embedding_fails(
        self,
    ) -> None:
        memory = self._memory(
            memory_id="calculator",
            content=(
                "Calculator API projem "
                "unittest kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
        )

        semantic = (
            SemanticMemoryRetriever(
                embedding_provider=(
                    FailingEmbeddingProvider()
                ),
            )
        )

        hybrid = (
            HybridMemoryRetriever(
                keyword_retriever=(
                    KeywordMemoryRetriever()
                ),
                semantic_retriever=(
                    semantic
                ),
            )
        )

        result = hybrid.retrieve(
            query=(
                "Calculator API "
                "ne kullanıyor?"
            ),
            memories=[
                memory
            ],
            limit=1,
        )

        self.assertEqual(
            result,
            [
                memory
            ],
        )

    def test_hybrid_retriever_can_return_semantic_only_match(
        self,
    ) -> None:
        calculator = self._memory(
            memory_id="calculator",
            content=(
                "Calculator API projem "
                "unittest kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
        )

        semantic = (
            SemanticMemoryRetriever(
                embedding_provider=(
                    RuleEmbeddingProvider()
                ),
                minimum_similarity=0.8,
            )
        )

        hybrid = (
            HybridMemoryRetriever(
                keyword_retriever=(
                    KeywordMemoryRetriever()
                ),
                semantic_retriever=(
                    semantic
                ),
            )
        )

        result = hybrid.retrieve(
            query=(
                "Hesap makinesi servisimin "
                "test altyapısı neydi?"
            ),
            memories=[
                calculator
            ],
            limit=1,
        )

        self.assertEqual(
            result,
            [
                calculator
            ],
        )

    def test_ollama_embedding_provider_accepts_batch_response(
        self,
    ) -> None:
        calls: list[
            dict
        ] = []

        def fake_embed_client(
            **kwargs,
        ):
            calls.append(
                kwargs
            )

            return {
                "embeddings": [
                    [
                        1.0,
                        0.0,
                    ],
                    [
                        0.0,
                        1.0,
                    ],
                ]
            }

        provider = (
            OllamaEmbeddingProvider(
                model_name="fake-embed",
                embed_client=(
                    fake_embed_client
                ),
            )
        )

        result = provider.embed(
            [
                "bir",
                "iki",
            ]
        )

        self.assertEqual(
            result,
            [
                [
                    1.0,
                    0.0,
                ],
                [
                    0.0,
                    1.0,
                ],
            ],
        )

        self.assertEqual(
            calls[0]["model"],
            "fake-embed",
        )

        self.assertEqual(
            calls[0]["input"],
            [
                "bir",
                "iki",
            ],
        )

    def test_ollama_embedding_provider_rejects_zero_vector(
        self,
    ) -> None:
        provider = (
            OllamaEmbeddingProvider(
                model_name="fake-embed",
                embed_client=(
                    lambda **_: {
                        "embeddings": [
                            [
                                0.0,
                                0.0,
                            ]
                        ]
                    }
                ),
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            provider.embed(
                [
                    "test"
                ]
            )

    def test_semantic_threshold_rejects_unrelated_memory(
        self,
    ) -> None:
        provider = (
            RuleEmbeddingProvider()
        )

        retriever = (
            SemanticMemoryRetriever(
                embedding_provider=provider,
                minimum_similarity=0.8,
            )
        )

        flutter = self._memory(
            memory_id="flutter",
            content=(
                "Flutter projem "
                "Riverpod kullanıyor."
            ),
            updated_at=(
                "2026-09-03"
                "T11:00:00+00:00"
            ),
        )

        result = retriever.retrieve(
            query=(
                "Hesap makinesi servisimin "
                "test altyapısı neydi?"
            ),
            memories=[
                flutter
            ],
            limit=1,
        )

        self.assertEqual(
            result,
            [],
        )


if __name__ == "__main__":
    unittest.main()