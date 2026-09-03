import re

from boru.profile.models import (
    ProfileUpdate,
)


class RuleBasedProfileExtractor:
    """
    Açıkça belirtilmiş kalıcı profil bilgilerini
    deterministik kurallarla çıkarır.

    V0.3'te bilinçli olarak muhafazakârdır.
    """

    _QUESTION_VALUES = {
        "ne",
        "nedir",
        "neydi",
        "neymiş",
        "ney",
        "hangi",
        "hangisi",
        "kim",
        "kaç",
    }

    _NAME_PATTERNS = (
        re.compile(
            (
                r"\b(?:benim\s+)?"
                r"adım\s+"
                r"(.+?)"
                r"(?:[.!?]|$)"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"\bismim\s+"
                r"(.+?)"
                r"(?:[.!?]|$)"
            ),
            re.IGNORECASE,
        ),
    )

    _COLOR_PATTERNS = (
        re.compile(
            (
                r"\b(?:benim\s+)?"
                r"favori\s+rengim\s+"
                r"(.+?)"
                r"(?:[.!?]|$)"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"\ben\s+sevdiğim\s+"
                r"renk\s+"
                r"(.+?)"
                r"(?:[.!?]|$)"
            ),
            re.IGNORECASE,
        ),
    )

    def extract(
        self,
        user_message: str,
    ) -> list[ProfileUpdate]:
        text = self._normalize(
            user_message
        )

        if not text:
            return []

        updates: list[
            ProfileUpdate
        ] = []

        name = self._first_value(
            text,
            self._NAME_PATTERNS,
        )

        if (
            name
            and not self._looks_like_question(
                name
            )
        ):
            updates.append(
                ProfileUpdate(
                    category="identity",
                    key="name",
                    value=name,
                )
            )

        color = self._first_value(
            text,
            self._COLOR_PATTERNS,
        )

        if (
            color
            and not self._looks_like_question(
                color
            )
        ):
            updates.append(
                ProfileUpdate(
                    category="preference",
                    key="favorite_color",
                    value=color.lower(),
                )
            )

        return updates

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value.strip().split()
        )

    def _first_value(
        self,
        text: str,
        patterns: tuple[
            re.Pattern[str],
            ...,
        ],
    ) -> str | None:
        for pattern in patterns:
            match = pattern.search(
                text
            )

            if not match:
                continue

            value = self._clean_value(
                match.group(1)
            )

            if value:
                return value

        return None

    @staticmethod
    def _clean_value(
        value: str,
    ) -> str:
        cleaned = " ".join(
            value.strip(
                " \t\r\n,;:-"
            ).split()
        )

        return cleaned[:80]

    def _looks_like_question(
        self,
        value: str,
    ) -> bool:
        if not value:
            return False

        first_word = (
            value
            .casefold()
            .split(
                maxsplit=1
            )[0]
        )

        return (
            first_word
            in self._QUESTION_VALUES
        )