import math
from collections.abc import Sequence
from typing import Any


class OllamaEmbeddingProvider:
    """
    Ollama embed API'sini semantic memory
    katmanına uyarlar.
    """

    def __init__(
        self,
        model_name: str,
        embed_client: Any = None,
    ):
        cleaned_model_name = (
            model_name.strip()
        )

        if not cleaned_model_name:
            raise ValueError(
                "Embedding model adı boş olamaz."
            )

        self._model_name = (
            cleaned_model_name
        )

        self._embed_client = (
            embed_client
            or self._default_embed_client()
        )

    @staticmethod
    def _default_embed_client():
        try:
            import ollama

        except ImportError as error:
            raise RuntimeError(
                (
                    "Ollama Python paketi "
                    "embedding için gerekli."
                )
            ) from error

        return ollama.embed

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        cleaned_texts = [
            text.strip()
            for text in texts
        ]

        if not cleaned_texts:
            return []

        if any(
            not text
            for text in cleaned_texts
        ):
            raise ValueError(
                (
                    "Embedding için boş "
                    "metin gönderilemez."
                )
            )

        response = self._embed_client(
            model=self._model_name,
            input=cleaned_texts,
        )

        raw_embeddings = self._field(
            response,
            "embeddings",
        )

        if raw_embeddings is None:
            raise RuntimeError(
                (
                    "Ollama embedding "
                    "yanıtında embeddings "
                    "alanı bulunamadı."
                )
            )

        embeddings = [
            [
                float(value)
                for value in vector
            ]
            for vector
            in raw_embeddings
        ]

        if (
            len(embeddings)
            != len(cleaned_texts)
        ):
            raise RuntimeError(
                (
                    "Ollama embedding sayısı "
                    "giriş sayısıyla eşleşmiyor."
                )
            )

        self._validate_vectors(
            embeddings
        )

        return embeddings

    @staticmethod
    def _field(
        value: Any,
        name: str,
        default: Any = None,
    ) -> Any:
        if isinstance(
            value,
            dict,
        ):
            return value.get(
                name,
                default,
            )

        return getattr(
            value,
            name,
            default,
        )

    @staticmethod
    def _validate_vectors(
        embeddings: list[
            list[float]
        ],
    ) -> None:
        if not embeddings:
            return

        expected_dimension = len(
            embeddings[0]
        )

        if expected_dimension < 1:
            raise RuntimeError(
                (
                    "Embedding vektörü "
                    "boş olamaz."
                )
            )

        for vector in embeddings:
            if (
                len(vector)
                != expected_dimension
            ):
                raise RuntimeError(
                    (
                        "Embedding vektör "
                        "boyutları birbiriyle "
                        "eşleşmiyor."
                    )
                )

            if any(
                not math.isfinite(value)
                for value in vector
            ):
                raise RuntimeError(
                    (
                        "Embedding vektörü "
                        "geçersiz sayı içeriyor."
                    )
                )

            norm_squared = sum(
                value * value
                for value in vector
            )

            if norm_squared <= 0.0:
                raise RuntimeError(
                    (
                        "Embedding vektörünün "
                        "normu sıfır olamaz."
                    )
                )