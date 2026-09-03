import re

from boru.profile.contracts import (
    ProfileService,
)


class RuleBasedProfileQueryResolver:
    """
    Bilinen profil alanlarına yönelik basit
    kullanıcı sorularını deterministik olarak
    yanıtlar.

    Bu sorguların LLM'e bırakılmasını engeller.
    """

    _NAME_PATTERNS = (
        re.compile(
            r"^(?:benim\s+)?adım\s+ne(?:ydi)?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^ismim\s+ne(?:ydi)?$",
            re.IGNORECASE,
        ),
    )

    _FAVORITE_COLOR_PATTERNS = (
        re.compile(
            (
                r"^(?:benim\s+)?"
                r"favori\s+rengim\s+"
                r"ne(?:ydi)?$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^en\s+sevdiğim\s+"
                r"renk\s+ne(?:ydi)?$"
            ),
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        profile_service: ProfileService,
    ):
        self._profile_service = (
            profile_service
        )

    def resolve(
        self,
        user_message: str,
    ) -> str | None:
        normalized_message = (
            self._normalize(
                user_message
            )
        )

        if not normalized_message:
            return None

        if self._matches(
            normalized_message,
            self._NAME_PATTERNS,
        ):
            return self._resolve_name()

        if self._matches(
            normalized_message,
            self._FAVORITE_COLOR_PATTERNS,
        ):
            return (
                self._resolve_favorite_color()
            )

        return None

    def _resolve_name(
        self,
    ) -> str:
        name = (
            self._profile_service
            .get_name()
        )

        if not name:
            return (
                "Adını henüz kalıcı "
                "olarak bilmiyorum."
            )

        return f"Adın {name}."

    def _resolve_favorite_color(
        self,
    ) -> str:
        color = (
            self._profile_service
            .get_preference(
                "favorite_color"
            )
        )

        if not color:
            return (
                "Favori rengini henüz "
                "kalıcı olarak bilmiyorum."
            )

        return (
            f"Favori rengin {color}."
        )

    @staticmethod
    def _matches(
        value: str,
        patterns: tuple[
            re.Pattern[str],
            ...,
        ],
    ) -> bool:
        return any(
            pattern.fullmatch(value)
            is not None
            for pattern in patterns
        )

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        cleaned = (
            value.strip()
            .rstrip(".!?")
            .strip()
        )

        return " ".join(
            cleaned.split()
        )