import re


class ExplicitMemoryExtractor:
    """
    Yalnızca açık hatırla/kaydet/unutma
    ifadelerini uzun süreli hafıza adayı yapar.
    """

    _PATTERNS = (
        re.compile(
            (
                r"^(?:bunu|şunu)\s+"
                r"hatırla\s*[:,-]?\s*"
                r"(.+)$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^hatırla\s*[:,-]\s*"
                r"(.+)$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^unutma\s*[:,-]?\s*"
                r"(.+)$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^hafızana\s+kaydet"
                r"\s*[:,-]?\s*(.+)$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^bunu\s+hafızana\s+"
                r"kaydet\s*[:,-]?\s*"
                r"(.+)$"
            ),
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        max_length: int = 500,
    ):
        if max_length < 1:
            raise ValueError(
                (
                    "max_length "
                    "en az 1 olmalıdır."
                )
            )

        self._max_length = (
            max_length
        )

    def extract(
        self,
        user_message: str,
    ) -> list[str]:
        text = self._normalize(
            user_message
        )

        if not text:
            return []

        for pattern in self._PATTERNS:
            match = pattern.fullmatch(
                text
            )

            if not match:
                continue

            content = (
                self._clean_content(
                    match.group(1)
                )
            )

            if content:
                return [content]

        return []

    def _clean_content(
        self,
        value: str,
    ) -> str:
        cleaned = " ".join(
            value
            .strip(
                " \t\r\n,;:-"
            )
            .split()
        )

        return cleaned[
            :self._max_length
        ]

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value.strip().split()
        )