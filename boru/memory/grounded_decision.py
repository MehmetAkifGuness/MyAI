import re

from boru.memory.contracts import (
    MemoryDecisionEngine,
)
from boru.memory.models import (
    MemoryDecision,
)


class GroundedMemoryDecisionEngine:
    """
    LLM hafıza kararını kaynak kullanıcı mesajına karşı doğrular.

    Amaç, modelin kullanıcının söylemediği teknoloji, framework,
    veritabanı veya başka bir değeri uzun süreli hafızaya eklemesini
    fail-closed biçimde engellemektir.
    """

    _TOKEN_PATTERN = re.compile(
        r"[\w#+.-]+",
        re.UNICODE,
    )

    _IGNORED_CONTENT_TOKENS = {
        "a",
        "an",
        "and",
        "bir",
        "bu",
        "da",
        "de",
        "for",
        "ile",
        "in",
        "için",
        "kullanılan",
        "kullanıyor",
        "kullanıyorum",
        "kullanıyorsun",
        "kullanıyoruz",
        "kullanmak",
        "of",
        "olarak",
        "the",
        "ve",
    }

    def __init__(
        self,
        inner: MemoryDecisionEngine,
        minimum_content_coverage: float = 0.55,
    ):
        if not 0.0 <= minimum_content_coverage <= 1.0:
            raise ValueError(
                (
                    "minimum_content_coverage "
                    "0.0 ile 1.0 arasında olmalıdır."
                )
            )

        self._inner = inner
        self._minimum_content_coverage = (
            minimum_content_coverage
        )

    def decide(
        self,
        user_message: str,
    ) -> MemoryDecision:
        decision = self._inner.decide(
            user_message
        )

        if not decision.should_save:
            return decision

        source = " ".join(
            user_message.strip().split()
        )

        if not source:
            return self._reject(
                "Kaynak kullanıcı mesajı boş."
            )

        if (
            decision.value
            and not self._is_value_grounded(
                decision.value,
                source,
            )
        ):
            return self._reject(
                (
                    "Hafıza değeri kullanıcı mesajında "
                    "doğrulanamadı."
                )
            )

        if (
            decision.content
            and not self._is_content_grounded(
                decision.content,
                source,
            )
        ):
            return self._reject(
                (
                    "Hafıza içeriği kullanıcı mesajına "
                    "yeterince dayanmıyor."
                )
            )

        return decision

    def _is_value_grounded(
        self,
        value: str,
        source: str,
    ) -> bool:
        value_normalized = self._compact(
            value
        )

        source_normalized = self._compact(
            source
        )

        if not value_normalized:
            return False

        return (
            value_normalized
            in source_normalized
        )

    def _is_content_grounded(
        self,
        content: str,
        source: str,
    ) -> bool:
        content_tokens = self._significant_tokens(
            content
        )

        if not content_tokens:
            return False

        source_tokens = set(
            self._tokens(
                source
            )
        )

        matched = sum(
            1
            for token in content_tokens
            if token in source_tokens
        )

        coverage = (
            matched
            / len(content_tokens)
        )

        return (
            coverage
            >= self._minimum_content_coverage
        )

    def _significant_tokens(
        self,
        value: str,
    ) -> list[str]:
        return [
            token
            for token in self._tokens(value)
            if token
            not in self._IGNORED_CONTENT_TOKENS
        ]

    @classmethod
    def _tokens(
        cls,
        value: str,
    ) -> list[str]:
        return [
            token.casefold()
            for token
            in cls._TOKEN_PATTERN.findall(
                value
            )
        ]

    @classmethod
    def _compact(
        cls,
        value: str,
    ) -> str:
        return "".join(
            cls._tokens(value)
        )

    @staticmethod
    def _reject(
        reason: str,
    ) -> MemoryDecision:
        return MemoryDecision(
            should_save=False,
            reason=reason,
        )