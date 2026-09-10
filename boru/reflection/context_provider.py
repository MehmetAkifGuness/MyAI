from __future__ import annotations

import re
from typing import Sequence

from boru.reflection.engine import SelfReflectionEngine


class ReflectionContextProvider:
    """
    Kullanıcının mesajında veya hedef dosyalarda geçen konulara ilişkin
    önceden çıkarılmış öz-iyileştirme derslerini sistem bağlamına enjekte eder.
    """

    _FILE_PATTERN = re.compile(
        r"\b(?:[a-zA-Z0-9_\-\./\\]+\.(?:py|json|md|txt|sql|html|css|js|yaml|yml|toml))\b",
        re.IGNORECASE,
    )

    def __init__(self, engine: SelfReflectionEngine, max_lessons: int = 4):
        self._engine = engine
        self._max_lessons = max_lessons

    def build_context(self, user_message: str) -> str:
        matches = self._FILE_PATTERN.findall(user_message)
        clean_paths = tuple(dict.fromkeys(matches))

        records = []
        if clean_paths:
            records = self._engine.get_lessons_for_targets(clean_paths)
        else:
            # Belirli dosya geçmiyorsa en güncel genel dersleri al
            records = self._engine._repository.read_records()[-self._max_lessons:]
            records.reverse()

        if not records:
            return ""

        selected = records[:self._max_lessons]
        lessons_text = "\n".join(f"- [{r.verdict.value}] {r.lesson}" for r in selected)

        return (
            "[Öz-İyileştirme Hafızası — Geçmiş Görevlerden Çıkarılan Dersler]\n"
            f"{lessons_text}\n"
            "Bu kuralları ve önceki hatalardan çıkarılan tecrübeleri uygulayarak benzer hataları tekrarlama."
        )
