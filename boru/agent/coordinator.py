import re

from boru.agent.contracts import AgentRunner


class GeneralAgentCoordinator:
    _PATTERN = re.compile(r"^\s*(?:ajan|kod tabanını araştır)\s*:\s*(.*)$", re.IGNORECASE | re.DOTALL)
    _CODE_REFERENCE = re.compile(
        r"(?:\b[A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü0-9_]*[A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü0-9_]*\b|"
        r"\b[A-Za-z0-9_./\\-]+\.(?:py|js|ts|java|cs|dart|go|rs)\b)"
    )
    _NAMED_REFERENCE = re.compile(r"\b[A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü0-9_]{2,}\b")
    _QUESTION_CUES = (
        "hangi dosya",
        "nerede",
        "nasıl",
        "ne yap",
        "ana adım",
        "akışı",
        "sorumluluğu",
        "kim kullan",
        "nereden çağr",
    )
    _PROJECT_CUES = ("bu proje", "projede", "kod tabanı", "kaynak kod")
    _CONTROL_COMMAND = re.compile(
        r"^\s*(?:kodla|iyileştir|dosya oluştur|dosya sil|düzenle|task çalıştır|"
        r"görev planla|test ajanı|güvenlik tara|kod incele)\s*:"
        ,
        re.IGNORECASE,
    )

    def __init__(self, agent: AgentRunner) -> None:
        self._agent = agent

    def resolve(self, user_message: str) -> str | None:
        match = self._PATTERN.match(user_message)
        if match is not None:
            objective = match.group(1).strip()
        elif self._is_automatic_candidate(user_message):
            objective = user_message.strip()
        else:
            return None
        if not objective:
            return "Ajan hedefi eksik. Örnek: ajan: kullanıcı mesajı hangi sınıfta işleniyor?"
        try:
            return self._agent.run(objective)
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            return f"Ajan görevi güvenli biçimde tamamlanamadı: {error}"

    @classmethod
    def _is_automatic_candidate(cls, user_message: str) -> bool:
        if cls._CONTROL_COMMAND.match(user_message):
            return False
        folded = " ".join(user_message.casefold().split())
        has_question = any(cue in folded for cue in cls._QUESTION_CUES)
        has_project_context = any(cue in folded for cue in cls._PROJECT_CUES)
        has_location_question = "hangi dosya" in folded
        has_code_path = re.search(r'\b[\w./\\-]+\.(?:py|js|ts|java|cs|dart|go|rs)\b', user_message) is not None
        has_symbol_context = any(cue in folded for cue in ('sınıfı', 'sınıfın', 'fonksiyonu', 'metodu', 'modülü', 'sembolü'))
        return has_question and (
            has_code_path
            or (has_symbol_context and cls._CODE_REFERENCE.search(user_message) is not None)
            or (has_location_question and cls._NAMED_REFERENCE.search(user_message) is not None)
            or has_project_context
        )
