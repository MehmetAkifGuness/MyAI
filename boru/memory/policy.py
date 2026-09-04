import re

from boru.memory.contracts import (
    MemoryForgetParser,
)


class ConservativeMemoryDecisionGate:
    """LLM hafıza kararını yalnızca uygun aday mesajlarda çalıştırır."""

    _QUESTION_PREFIXES = (
        "acaba ",
        "hangi ",
        "kaç ",
        "kim ",
        "ne ",
        "neden ",
        "nasıl ",
        "nerede ",
        "ne zaman ",
    )

    _TRANSIENT_PATTERNS = (
        re.compile(r"\bbugün\b", re.IGNORECASE),
        re.compile(r"\bdün\b", re.IGNORECASE),
        re.compile(r"\byarın\b", re.IGNORECASE),
        re.compile(r"\bşu\s+an\b", re.IGNORECASE),
        re.compile(r"\bşimdi\b", re.IGNORECASE),
        re.compile(r"\baz\s+önce\b", re.IGNORECASE),
        re.compile(r"\bbu\s+akşam\b", re.IGNORECASE),
        re.compile(r"\bbu\s+sabah\b", re.IGNORECASE),
    )

    _MEMORY_META_PATTERNS = (
        re.compile(
            r"\b(?:unuttum|sildim|hatırladım)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bhafıza\s+kayd(?:ı|ını|ınım|ımız|ınız|ları|larını)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\buzun\s+süreli\s+hafıza\b",
            re.IGNORECASE,
        ),
    )

    _ONE_TIME_TASK_PATTERNS = (
        re.compile(
            r"\bdosyasını\s+(?:oku|göster|aç)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bdosyasının\s+içeriğini\s+(?:oku|göster)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bklasör(?:ünü|ündeki)\b.*\b(?:listele|göster)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bdosyaları\s+(?:listele|göster)\b",
            re.IGNORECASE,
        ),
    )

    _PROFILE_PATTERNS = (
        re.compile(r"\b(?:benim\s+)?adım\b", re.IGNORECASE),
        re.compile(r"\bismim\b", re.IGNORECASE),
        re.compile(r"\bfavori\s+rengim\b", re.IGNORECASE),
        re.compile(r"\ben\s+sevdiğim\s+renk\b", re.IGNORECASE),
    )

    _SECRET_PATTERNS = (
        re.compile(r"\bşifrem\b", re.IGNORECASE),
        re.compile(r"\bparolam\b", re.IGNORECASE),
        re.compile(r"\bpin(?:\s+kodum)?\b", re.IGNORECASE),
        re.compile(r"\bcvv\b", re.IGNORECASE),
        re.compile(r"\bkart\s+numaram\b", re.IGNORECASE),
        re.compile(r"\bkimlik\s+numaram\b", re.IGNORECASE),
    )

    _EXPLICIT_MEMORY_PREFIXES = (
        "bunu hatırla",
        "şunu hatırla",
        "hatırla:",
        "hatırla,",
        "unutma",
        "hafızana kaydet",
        "bunu hafızana kaydet",
    )

    _GREETINGS = {
        "merhaba",
        "selam",
        "selamlar",
        "günaydın",
        "iyi akşamlar",
        "iyi geceler",
    }

    def __init__(
        self,
        minimum_length: int = 12,
        forget_parser: MemoryForgetParser | None = None,
    ):
        if minimum_length < 1:
            raise ValueError(
                "minimum_length en az 1 olmalıdır."
            )

        self._minimum_length = (
            minimum_length
        )

        self._forget_parser = (
            forget_parser
        )

    def should_evaluate(
        self,
        user_message: str,
    ) -> bool:
        text = " ".join(
            user_message.strip().split()
        )

        if len(text) < self._minimum_length:
            return False

        if (
            self._forget_parser is not None
            and self._forget_parser.parse(text)
            is not None
        ):
            return False

        folded = text.casefold()
        stripped = folded.rstrip(".!?").strip()

        if stripped in self._GREETINGS:
            return False

        if "?" in text:
            return False

        if any(
            folded.startswith(prefix)
            for prefix in self._QUESTION_PREFIXES
        ):
            return False

        if any(
            folded.startswith(prefix)
            for prefix in self._EXPLICIT_MEMORY_PREFIXES
        ):
            return False

        if self._matches_any(
            text,
            self._TRANSIENT_PATTERNS,
        ):
            return False

        if self._matches_any(
            text,
            self._MEMORY_META_PATTERNS,
        ):
            return False

        if self._matches_any(
            text,
            self._ONE_TIME_TASK_PATTERNS,
        ):
            return False

        if self._matches_any(
            text,
            self._PROFILE_PATTERNS,
        ):
            return False

        if self._matches_any(
            text,
            self._SECRET_PATTERNS,
        ):
            return False

        return True

    @staticmethod
    def _matches_any(
        value: str,
        patterns: tuple[re.Pattern[str], ...],
    ) -> bool:
        return any(
            pattern.search(value)
            is not None
            for pattern in patterns
        )