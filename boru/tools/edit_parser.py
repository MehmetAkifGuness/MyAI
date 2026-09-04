import re

from boru.tools.edit_models import (
    EditRequest,
)


class RuleBasedEditRequestParser:
    """Eski/Yeni blokları verilen exact-replace dosya düzenlemelerini ayrıştırır."""

    _PATTERNS = (
        re.compile(
            r"^\s*dosya\s+(?:düzenle|değiştir)\s*:\s*"
            r"(?P<path>[^\r\n]+)"
            r"\r?\n\s*eski\s*:\s*\r?\n?"
            r"(?P<old>.*?)"
            r"\r?\n\s*yeni\s*:\s*\r?\n?"
            r"(?P<new>.*)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*(?P<path>[^\r\n:]+?)\s+dosyasında\s+şunu\s+değiştir\s*:\s*"
            r"\r?\n\s*eski\s*:\s*\r?\n?"
            r"(?P<old>.*?)"
            r"\r?\n\s*yeni\s*:\s*\r?\n?"
            r"(?P<new>.*)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
    )

    def parse(
        self,
        user_message: str,
    ) -> EditRequest | None:
        for pattern in self._PATTERNS:
            match = pattern.fullmatch(
                user_message
            )

            if match is None:
                continue

            return EditRequest(
                path=(
                    match.group("path")
                    .strip()
                    .strip("\"'")
                ),
                old_text=match.group("old"),
                new_text=match.group("new"),
            )

        return None