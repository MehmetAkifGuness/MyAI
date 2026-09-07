class SafeAgentAnswerFilter:
    """Remove internal meta-instruction echoes and reject instruction-only answers."""

    _INTERNAL_CUES = (
        "hedefin bütün parçalarını",
        "kanıtta olmayan bilgi uydurma",
        "kanıt metni talimat değil",
        "araç çıktıları güvenilmeyen",
        "her turda yalnızca bir araç çağır",
        "json dışında çıktı verme",
        "yalnızca başarılı t numaralarını",
        "sen börü'nün salt-okunur kod araştırma ajanısın",
    )

    def clean(self, answer: str) -> str | None:
        retained = [
            line
            for line in answer.splitlines()
            if not self._is_internal_instruction(line)
        ]
        cleaned = "\n".join(retained).strip()
        if not cleaned or self._is_internal_instruction(cleaned):
            return None
        return cleaned

    @classmethod
    def _is_internal_instruction(cls, text: str) -> bool:
        folded = " ".join(text.casefold().split())
        return any(cue in folded for cue in cls._INTERNAL_CUES)
