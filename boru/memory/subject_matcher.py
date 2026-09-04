import re
from threading import RLock

from boru.memory.contracts import (
    EmbeddingProvider,
    MemorySubjectMatcher,
)
from boru.memory.similarity import (
    cosine_similarity,
)


class ExactSubjectMatcher:
    """
    Subject adlarını normalize edilmiş metin
    eşitliği ile karşılaştırır.
    """

    def is_same_subject(
        self,
        left: str,
        right: str,
    ) -> bool:
        return (
            self._normalize(left)
            == self._normalize(right)
        )

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value
            .casefold()
            .strip()
            .split()
        )


class SemanticSubjectMatcher:
    """
    Subject kimliğini önce exact, sonra güvenli
    semantic karşılaştırma ile belirler.

    API, servis, proje ve uygulama gibi jenerik
    son ekler embedding karşılaştırmasından
    çıkarılır. Böylece ortak teknik tür ifadesi
    gerçek entity adını bastıramaz.

    İki çekirdek ad da tek kelimelik ve farklıysa
    semantic eşleştirme yapılmaz. Bu koruma,
    Auth API ile Calculator API gibi farklı kısa
    teknik adların yanlışlıkla birleştirilmesini
    engeller.

    Embedding hatalarında fail-closed davranır.
    """

    _TOKEN_PATTERN = re.compile(
        r"[\w#+.-]+",
        re.UNICODE,
    )

    _GENERIC_TRAILING_TOKENS = {
        "api",
        "app",
        "application",
        "uygulama",
        "service",
        "servis",
        "project",
        "proje",
        "system",
        "sistem",
        "backend",
        "frontend",
    }

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        minimum_similarity: float = 0.84,
    ):
        if not 0.0 <= minimum_similarity <= 1.0:
            raise ValueError(
                (
                    "minimum_similarity "
                    "0.0 ile 1.0 arasında "
                    "olmalıdır."
                )
            )

        self._embedding_provider = (
            embedding_provider
        )

        self._minimum_similarity = (
            minimum_similarity
        )

        self._exact_matcher = (
            ExactSubjectMatcher()
        )

        self._cache: dict[
            str,
            list[float],
        ] = {}

        self._lock = RLock()

    def is_same_subject(
        self,
        left: str,
        right: str,
    ) -> bool:
        cleaned_left = self._clean(
            left
        )

        cleaned_right = self._clean(
            right
        )

        if not cleaned_left or not cleaned_right:
            return False

        if self._exact_matcher.is_same_subject(
            cleaned_left,
            cleaned_right,
        ):
            return True

        left_core = self._identity_core(
            cleaned_left
        )

        right_core = self._identity_core(
            cleaned_right
        )

        if not left_core or not right_core:
            return False

        if self._exact_matcher.is_same_subject(
            left_core,
            right_core,
        ):
            return True

        if self._is_distinct_single_token_pair(
            left_core,
            right_core,
        ):
            return False

        try:
            left_vector, right_vector = (
                self._vectors(
                    left_core,
                    right_core,
                )
            )

        except Exception:
            return False

        return (
            cosine_similarity(
                left_vector,
                right_vector,
            )
            >= self._minimum_similarity
        )

    def _vectors(
        self,
        left_core: str,
        right_core: str,
    ) -> tuple[
        list[float],
        list[float],
    ]:
        left_key = self._normalize(
            left_core
        )

        right_key = self._normalize(
            right_core
        )

        with self._lock:
            missing: list[
                tuple[str, str]
            ] = []

            if left_key not in self._cache:
                missing.append(
                    (
                        left_key,
                        self._embedding_text(
                            left_core
                        ),
                    )
                )

            if right_key not in self._cache:
                missing.append(
                    (
                        right_key,
                        self._embedding_text(
                            right_core
                        ),
                    )
                )

        if missing:
            generated = (
                self._embedding_provider.embed(
                    [
                        text
                        for _, text
                        in missing
                    ]
                )
            )

            if len(generated) != len(missing):
                raise RuntimeError(
                    (
                        "Embedding provider "
                        "eksik subject vektörü "
                        "döndürdü."
                    )
                )

            with self._lock:
                for (
                    key,
                    _,
                ), vector in zip(
                    missing,
                    generated,
                ):
                    self._cache[key] = vector

        with self._lock:
            return (
                self._cache[left_key],
                self._cache[right_key],
            )

    @classmethod
    def _identity_core(
        cls,
        subject: str,
    ) -> str:
        tokens = cls._TOKEN_PATTERN.findall(
            subject
        )

        while (
            len(tokens) > 1
            and tokens[-1].casefold()
            in cls._GENERIC_TRAILING_TOKENS
        ):
            tokens.pop()

        return " ".join(
            tokens
        ).strip()

    @classmethod
    def _is_distinct_single_token_pair(
        cls,
        left_core: str,
        right_core: str,
    ) -> bool:
        left_tokens = cls._TOKEN_PATTERN.findall(
            left_core
        )

        right_tokens = cls._TOKEN_PATTERN.findall(
            right_core
        )

        if (
            len(left_tokens) != 1
            or len(right_tokens) != 1
        ):
            return False

        return (
            left_tokens[0].casefold()
            != right_tokens[0].casefold()
        )

    @classmethod
    def _embedding_text(
        cls,
        identity_core: str,
    ) -> str:
        return (
            f"{identity_core} API"
        )

    @staticmethod
    def _clean(
        value: str,
    ) -> str:
        return " ".join(
            value.strip().split()
        )

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value
            .casefold()
            .strip()
            .split()
        )


class AliasAwareSubjectMatcher:
    """
    Güvenilir subject alias gruplarını deterministik olarak
    eşleştirir; eşleşmeyen durumları başka bir matcher'a devreder.

    Bu katman özellikle dil çevirisi gibi embedding modelinin
    kararsız kalabileceği bilinen alias'lar için kullanılır.
    """

    _TOKEN_PATTERN = re.compile(
        r"[\w#+.-]+",
        re.UNICODE,
    )

    _GENERIC_TRAILING_TOKENS = {
        "api",
        "app",
        "application",
        "uygulama",
        "service",
        "servis",
        "project",
        "proje",
        "system",
        "sistem",
        "backend",
        "frontend",
    }

    def __init__(
        self,
        delegate: MemorySubjectMatcher,
        alias_groups: tuple[tuple[str, ...], ...],
    ):
        self._delegate = delegate
        self._alias_index = self._build_alias_index(
            alias_groups
        )

    def is_same_subject(
        self,
        left: str,
        right: str,
    ) -> bool:
        left_core = self._identity_core(
            left
        )

        right_core = self._identity_core(
            right
        )

        if not left_core or not right_core:
            return False

        left_key = self._normalize(
            left_core
        )

        right_key = self._normalize(
            right_core
        )

        if left_key == right_key:
            return True

        left_alias = self._alias_index.get(
            left_key
        )

        right_alias = self._alias_index.get(
            right_key
        )

        if (
            left_alias is not None
            and right_alias is not None
        ):
            return left_alias == right_alias

        return self._delegate.is_same_subject(
            left,
            right,
        )

    @classmethod
    def _build_alias_index(
        cls,
        alias_groups: tuple[tuple[str, ...], ...],
    ) -> dict[str, int]:
        index: dict[str, int] = {}

        for group_id, aliases in enumerate(
            alias_groups
        ):
            for alias in aliases:
                key = cls._normalize(
                    alias
                )

                if not key:
                    continue

                if key in index:
                    raise ValueError(
                        f"Tekrarlanan subject alias: {alias}"
                    )

                index[key] = group_id

        return index

    @classmethod
    def _identity_core(
        cls,
        subject: str,
    ) -> str:
        tokens = cls._TOKEN_PATTERN.findall(
            subject
        )

        while (
            len(tokens) > 1
            and tokens[-1].casefold()
            in cls._GENERIC_TRAILING_TOKENS
        ):
            tokens.pop()

        return " ".join(
            tokens
        ).strip()

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value
            .casefold()
            .strip()
            .split()
        )