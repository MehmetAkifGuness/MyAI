import re

from boru.tools.project_edit_models import (
    ProjectEditRequest,
)


class RuleBasedProjectEditRequestParser:
    """Açık project-level düzenleme komutlarını yakalar."""

    _PATTERNS = (
        re.compile(
            r"^\s*proje\s+düzenle\s*:\s*(?P<instruction>.+)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*projede\s+(?P<instruction>.+)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*projedeki\s+(?P<instruction>.+)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
    )

    _ACTION_PATTERN = re.compile(
        r"\b(?:ekle|değiştir|degistir|düzenle|duzenle|"
        r"güncelle|guncelle|ayarla|uyarla|kullan|bağla|bagla|"
        r"uygula|düzelt|duzelt|yap)\b",
        re.IGNORECASE,
    )

    def parse(
        self,
        user_message: str,
    ) -> ProjectEditRequest | None:
        for pattern in self._PATTERNS:
            match = pattern.fullmatch(
                user_message
            )

            if match is None:
                continue

            instruction = match.group(
                "instruction"
            ).strip()

            if self._ACTION_PATTERN.search(
                instruction
            ) is None:
                return None

            return ProjectEditRequest(
                instruction=instruction
            )

        return None