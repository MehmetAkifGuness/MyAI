import json

from boru.agent.contracts import StructuredChatModel
from boru.models import ChatMessage


class GroundedAnswerVerifier:
    """Koşul ve ret açıklamalarını aynı kaynak kanıtıyla ikinci kez doğrular."""

    _TRIGGERS = (
        "engell",
        "reddet",
        "doğrula",
        "koşul",
        "kanıtsız",
        "none",
    )
    _SCHEMA = {
        "type": "object",
        "properties": {
            "supported": {"type": "boolean"},
            "corrected_answer": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["supported", "corrected_answer", "reason"],
        "additionalProperties": False,
    }
    _SYSTEM_PROMPT = (
        "Aday yanıtı yalnızca kaynak kanıtıyla denetle ve düzeltilmiş nihai yanıtı Türkçe yaz. "
        "Özellikle boolean olumsuzluklarını tersine çevirme: `if not X: return None`, X yoksa "
        "veya yanlışsa reddedildiği anlamına gelir; X varsa reddedildiği anlamına gelmez. "
        "Adaydaki desteklenmeyen iddiaları çıkar. JSON dışında çıktı verme."
    )

    def __init__(self, model: StructuredChatModel) -> None:
        self._model = model

    def verify(self, objective: str, candidate: str, evidence: str) -> str | None:
        if not self._needs_verification(objective, candidate):
            return candidate
        try:
            raw = self._model.generate_structured(
                [
                    ChatMessage(role="system", content=self._SYSTEM_PROMPT),
                    ChatMessage(
                        role="user",
                        content=(
                            f"HEDEF:\n{objective}\n\nADAY YANIT:\n{candidate}\n\n"
                            f"KAYNAK KANITI:\n{evidence}"
                        ),
                    ),
                ],
                self._SCHEMA,
            )
            data = self._extract_object(raw)
            supported = data.get("supported")
            corrected = data.get("corrected_answer")
            reason = data.get("reason")
            if not isinstance(supported, bool):
                return None
            if not isinstance(corrected, str) or not isinstance(reason, str):
                return None
            cleaned = corrected.strip()
            return cleaned or (candidate if supported else None)
        except (OSError, RuntimeError, TimeoutError, ValueError):
            return None

    @classmethod
    def _needs_verification(cls, objective: str, candidate: str) -> bool:
        folded = objective.casefold()
        return any(trigger in folded for trigger in cls._TRIGGERS)

    @staticmethod
    def _extract_object(raw_output: str) -> dict[str, object]:
        decoder = json.JSONDecoder()
        text = raw_output.strip()
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                return candidate
        raise ValueError("Doğrulayıcı geçerli JSON nesnesi döndürmedi.")
