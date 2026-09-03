import json
from typing import Any

from boru.contracts import (
    ChatModel,
)
from boru.memory.models import (
    MemoryDecision,
)
from boru.models import (
    ChatMessage,
)


class LLMMemoryDecisionEngine:
    """
    LLM ile kontrollü ve mümkünse
    yapılandırılmış hafıza kararı üretir.
    """

    def __init__(
        self,
        chat_model: ChatModel,
        max_content_length: int = 500,
        max_field_length: int = 120,
    ):
        if max_content_length < 1:
            raise ValueError(
                (
                    "max_content_length "
                    "en az 1 olmalıdır."
                )
            )

        if max_field_length < 1:
            raise ValueError(
                (
                    "max_field_length "
                    "en az 1 olmalıdır."
                )
            )

        self._chat_model = (
            chat_model
        )

        self._max_content_length = (
            max_content_length
        )

        self._max_field_length = (
            max_field_length
        )

    def decide(
        self,
        user_message: str,
    ) -> MemoryDecision:
        text = " ".join(
            user_message
            .strip()
            .split()
        )

        if not text:
            return MemoryDecision(
                should_save=False,
                reason="Boş mesaj.",
            )

        messages = [
            ChatMessage(
                role="system",
                content=(
                    self._build_system_prompt()
                ),
            ),
            ChatMessage(
                role="user",
                content=text,
            ),
        ]

        try:
            raw_response = (
                self._chat_model
                .generate(messages)
                .strip()
            )

            payload = (
                self._parse_json_object(
                    raw_response
                )
            )

            return self._to_decision(
                payload
            )

        except Exception:
            return MemoryDecision(
                should_save=False,
                reason=(
                    "Hafıza kararı güvenilir "
                    "biçimde üretilemedi."
                ),
            )

    def _to_decision(
        self,
        payload: dict[str, Any],
    ) -> MemoryDecision:
        should_save = (
            payload.get(
                "save"
            )
        )

        if not isinstance(
            should_save,
            bool,
        ):
            return MemoryDecision(
                should_save=False,
                reason=(
                    "Geçersiz save alanı."
                ),
            )

        reason = (
            self._clean_field(
                payload.get(
                    "reason"
                ),
                200,
            )
            or ""
        )

        if not should_save:
            return MemoryDecision(
                should_save=False,
                reason=reason,
            )

        content = (
            self._clean_field(
                payload.get(
                    "content"
                ),
                self._max_content_length,
            )
        )

        if not content:
            return MemoryDecision(
                should_save=False,
                reason=(
                    "Kaydedilecek içerik boş."
                ),
            )

        subject = (
            self._clean_field(
                payload.get(
                    "subject"
                ),
                self._max_field_length,
            )
        )

        relation = (
            self._clean_field(
                payload.get(
                    "relation"
                ),
                self._max_field_length,
            )
        )

        value = (
            self._clean_field(
                payload.get(
                    "value"
                ),
                self._max_field_length,
            )
        )

        if (
            any(
                (
                    subject,
                    relation,
                    value,
                )
            )
            and not all(
                (
                    subject,
                    relation,
                    value,
                )
            )
        ):
            subject = None
            relation = None
            value = None

        return MemoryDecision(
            should_save=True,
            content=content,
            reason=reason,
            subject=subject,
            relation=relation,
            value=value,
        )

    @staticmethod
    def _parse_json_object(
        raw_response: str,
    ) -> dict[str, Any]:
        start = (
            raw_response.find("{")
        )

        end = (
            raw_response.rfind("}")
        )

        if (
            start < 0
            or end < start
        ):
            raise ValueError(
                (
                    "JSON nesnesi "
                    "bulunamadı."
                )
            )

        payload = json.loads(
            raw_response[
                start:end + 1
            ]
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                (
                    "JSON nesnesi "
                    "bekleniyordu."
                )
            )

        return payload

    @staticmethod
    def _clean_field(
        value: Any,
        limit: int,
    ) -> str | None:
        if value is None:
            return None

        cleaned = " ".join(
            str(value)
            .strip()
            .split()
        )[:limit]

        return cleaned or None

    @staticmethod
    def _build_system_prompt(
    ) -> str:
        return (
            "Görevin, kullanıcının son "
            "mesajındaki bilginin uzun "
            "süreli hafızaya kaydedilmeye "
            "değer olup olmadığına karar "
            "vermektir. Yalnızca JSON "
            "döndür. Şema: "
            '{"save": true|false, '
            '"content": "kısa kalıcı bilgi", '
            '"subject": "konu veya null", '
            '"relation": "ilişki veya null", '
            '"value": "değer veya null", '
            '"reason": "kısa neden"}. '
            "Yalnızca gelecekteki "
            "konuşmalarda anlamlı biçimde "
            "tekrar işe yarayacak, nispeten "
            "kalıcı proje kararlarını, "
            "kullanılan teknolojileri, "
            "çalışma tercihlerini veya uzun "
            "süre devam edecek bağlamsal "
            "bilgileri kaydet. "
            "Selamlaşmaları, soruları, anlık "
            "durumları, bugün/yarın gibi "
            "geçici bilgileri, tek seferlik "
            "görevleri ve tahminleri "
            "kaydetme. Kullanıcının adı ve "
            "favori renk gibi yapılandırılmış "
            "profil bilgilerini kaydetme; "
            "bunlar ayrı profil sistemi "
            "tarafından yönetiliyor. Şifre, "
            "parola, PIN, kart bilgisi, "
            "kimlik numarası veya benzeri "
            "sırları asla kaydetme. Bilgi "
            "subject-relation-value biçiminde "
            "güvenilir şekilde ifade "
            "edilebiliyorsa üç alanı da "
            "doldur; emin değilsen üçünü de "
            "null yap. Aynı konuya ait "
            "değişebilir bir özellik için "
            "relation sabit ve kısa olmalıdır; "
            "örnek relation değerleri "
            "test_framework, "
            "backend_framework, database, "
            "state_management. save=true ise "
            "content alanını kullanıcının "
            "söylediği bilgiyi bozmadan tek "
            "ve kısa bir cümle halinde yaz. "
            "JSON dışında hiçbir şey üretme."
        )