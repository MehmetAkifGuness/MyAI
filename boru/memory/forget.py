import re
from threading import RLock

from boru.memory.contracts import (
    MemoryForgetParser,
    MemoryService,
)
from boru.memory.models import (
    MemoryForgetMode,
    MemoryForgetRequest,
)


class RuleBasedMemoryForgetParser:
    """
    Açık uzun süreli hafıza silme komutlarını
    deterministik isteklere dönüştürür.

    Relation belirtilen komutlar TARGETED,
    yalnızca proje/subject belirtilen doğal
    komutlar SUBJECT olarak sınıflandırılır.
    Belirsiz "bu bilgiyi sil" komutları ise
    güvenli biçimde AMBIGUOUS kalır.
    """

    _CONFIRM_ALL_PATTERN = re.compile(
        r"^tüm\s+uzun\s+süreli\s+hafızamı\s+silmeyi\s+onaylıyorum$",
        re.IGNORECASE,
    )

    _CANCEL_PATTERNS = (
        re.compile(r"^iptal$", re.IGNORECASE),
        re.compile(r"^iptal\s+et$", re.IGNORECASE),
        re.compile(r"^vazgeçtim$", re.IGNORECASE),
    )

    _ALL_PATTERNS = (
        re.compile(r"^her\s+şeyi\s+unut$", re.IGNORECASE),
        re.compile(r"^tüm\s+hafızanı\s+sil$", re.IGNORECASE),
        re.compile(r"^tüm\s+uzun\s+süreli\s+hafızanı\s+sil$", re.IGNORECASE),
        re.compile(r"^hafızandaki\s+her\s+şeyi\s+sil$", re.IGNORECASE),
        re.compile(r"^uzun\s+süreli\s+hafızandaki\s+her\s+şeyi\s+sil$", re.IGNORECASE),
    )

    _LATEST_PATTERNS = (
        re.compile(r"^en\s+son\s+kaydettiğin\s+bilgiyi\s+unut$", re.IGNORECASE),
        re.compile(r"^en\s+son\s+hafıza\s+kaydını\s+sil$", re.IGNORECASE),
        re.compile(r"^son\s+hafıza\s+kaydını\s+sil$", re.IGNORECASE),
        re.compile(r"^en\s+son\s+hatırladığın\s+bilgiyi\s+unut$", re.IGNORECASE),
    )

    _AMBIGUOUS_PATTERNS = (
        re.compile(r"^bu\s+bilgiyi\s+(?:unut|sil)$", re.IGNORECASE),
        re.compile(r"^bu\s+bilgiyi\s+hafızandan\s+sil$", re.IGNORECASE),
        re.compile(r"^bunu\s+(?:unut|sil)$", re.IGNORECASE),
        re.compile(r"^bunu\s+hafızandan\s+sil$", re.IGNORECASE),
    )

    _RELATION_PATTERNS = (
        (
            re.compile(
                r"\b(?:test\s+framework(?:ü|u)?|test\s+altyapısı|test\s+sistemi)\b",
                re.IGNORECASE,
            ),
            "test_framework",
        ),
        (
            re.compile(
                r"\b(?:backend\s+framework(?:ü|u)?|backend)\b",
                re.IGNORECASE,
            ),
            "backend_framework",
        ),
        (
            re.compile(
                r"\b(?:state\s+management|durum\s+yönetimi)\b",
                re.IGNORECASE,
            ),
            "state_management",
        ),
        (
            re.compile(
                r"\b(?:veritabanı|database)\b",
                re.IGNORECASE,
            ),
            "database",
        ),
    )

    _TARGET_ACTION_PATTERN = re.compile(
        (
            r"^\s*(?:bilgisini|kaydını)?\s*"
            r"(?:unut|sil|hafızandan\s+sil|hafızadan\s+sil|artık\s+hatırlama)$"
        ),
        re.IGNORECASE,
    )

    _SUBJECT_PATTERNS = (
        re.compile(
            (
                r"^(?P<subject>.+?)"
                r"(?:'(?:nin|nın|nun|nün)|\s+(?:nin|nın|nun|nün))\s+"
                r"(?:tüm\s+)?(?:verilerini|bilgilerini)\s+"
                r"(?:unut|sil|hafızandan\s+sil)$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^(?P<subject>.+?)\s+hakkında\s+"
                r"(?:bildiklerini|bildiğin\s+her\s+şeyi)\s+"
                r"(?:unut|sil|hafızandan\s+sil)$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^(?P<subject>.+?)\s+ile\s+ilgili\s+"
                r"(?:her\s+şeyi|bilgileri|bildiklerini)\s+"
                r"(?:unut|sil|hafızandan\s+sil)$"
            ),
            re.IGNORECASE,
        ),
        re.compile(
            (
                r"^(?P<subject>.+?)\s+bilgilerini\s+"
                r"(?:unut|sil|hafızandan\s+sil)$"
            ),
            re.IGNORECASE,
        ),
    )

    _SCOPE_SUFFIX_PATTERN = re.compile(
        r"\s+(?:projemin|uygulamamın|servisimin|sistemimin)$",
        re.IGNORECASE,
    )

    _APOSTROPHE_SUFFIX_PATTERN = re.compile(
        (
            r"['](?:nin|nın|nun|nün|in|ın|un|ün|"
            r"min|mın|mun|mün|imin|ımın|umun|ümün)$"
        ),
        re.IGNORECASE,
    )

    def parse(
        self,
        user_message: str,
    ) -> MemoryForgetRequest | None:
        normalized = self._normalize(
            user_message
        )

        if not normalized:
            return None

        if self._CONFIRM_ALL_PATTERN.fullmatch(
            normalized
        ):
            return MemoryForgetRequest(
                mode=MemoryForgetMode.CONFIRM_ALL
            )

        if self._matches_any(
            normalized,
            self._CANCEL_PATTERNS,
        ):
            return MemoryForgetRequest(
                mode=MemoryForgetMode.CANCEL
            )

        if self._matches_any(
            normalized,
            self._ALL_PATTERNS,
        ):
            return MemoryForgetRequest(
                mode=MemoryForgetMode.ALL
            )

        if self._matches_any(
            normalized,
            self._LATEST_PATTERNS,
        ):
            return MemoryForgetRequest(
                mode=MemoryForgetMode.LATEST
            )

        if self._matches_any(
            normalized,
            self._AMBIGUOUS_PATTERNS,
        ):
            return MemoryForgetRequest(
                mode=MemoryForgetMode.AMBIGUOUS
            )

        targeted_request = self._parse_targeted(
            normalized
        )

        if targeted_request is not None:
            return targeted_request

        return self._parse_subject(
            normalized
        )

    def _parse_targeted(
        self,
        normalized: str,
    ) -> MemoryForgetRequest | None:
        for pattern, relation in self._RELATION_PATTERNS:
            match = pattern.search(
                normalized
            )

            if match is None:
                continue

            remainder = normalized[
                match.end():
            ].strip()

            if not self._TARGET_ACTION_PATTERN.fullmatch(
                remainder
            ):
                continue

            subject = self._clean_subject(
                normalized[:match.start()]
            )

            if not subject:
                return None

            return MemoryForgetRequest(
                mode=MemoryForgetMode.TARGETED,
                subject=subject,
                relation=relation,
            )

        return None

    def _parse_subject(
        self,
        normalized: str,
    ) -> MemoryForgetRequest | None:
        for pattern in self._SUBJECT_PATTERNS:
            match = pattern.fullmatch(
                normalized
            )

            if match is None:
                continue

            subject = self._clean_subject(
                match.group("subject")
            )

            if not subject:
                return None

            return MemoryForgetRequest(
                mode=MemoryForgetMode.SUBJECT,
                subject=subject,
            )

        return None

    @classmethod
    def _clean_subject(
        cls,
        value: str,
    ) -> str:
        cleaned = " ".join(
            value.strip().split()
        )

        cleaned = cls._SCOPE_SUFFIX_PATTERN.sub(
            "",
            cleaned,
        ).strip()

        cleaned = cls._APOSTROPHE_SUFFIX_PATTERN.sub(
            "",
            cleaned,
        ).strip()

        return cleaned.strip(
            " \t\r\n,;:-.!?"
        )[:120]

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        cleaned = (
            value
            .replace("’", "'")
            .strip()
            .rstrip(".!?")
            .strip()
        )

        return " ".join(
            cleaned.split()
        )

    @staticmethod
    def _matches_any(
        value: str,
        patterns: tuple[re.Pattern[str], ...],
    ) -> bool:
        return any(
            pattern.fullmatch(value)
            is not None
            for pattern in patterns
        )


class RuleBasedMemoryForgetResolver:
    """
    Hafıza silme komutlarını LLM'e bırakmadan
    güvenli biçimde uygular.

    Tüm uzun süreli hafızayı silme işlemi iki
    aşamalıdır. Açıkça belirtilen tek bir
    subject ise kendi kapsamındaki tüm uzun
    süreli kayıtlarla birlikte silinebilir.
    """

    _ALL_CONFIRMATION_TEXT = (
        "Tüm uzun süreli hafızamı silmeyi "
        "onaylıyorum."
    )

    def __init__(
        self,
        memory_service: MemoryService,
        parser: MemoryForgetParser,
    ):
        self._memory_service = (
            memory_service
        )

        self._parser = parser
        self._pending_clear_all = False
        self._lock = RLock()

    def resolve(
        self,
        user_message: str,
    ) -> str | None:
        request = self._parser.parse(
            user_message
        )

        with self._lock:
            if request is None:
                self._pending_clear_all = False
                return None

            if request.mode is MemoryForgetMode.ALL:
                self._pending_clear_all = True
                return (
                    "Tüm uzun süreli hafıza kayıtlarını "
                    "silmek üzeresin. Kalıcı profil bilgileri "
                    "bu işlemden etkilenmez. Devam etmek için "
                    f"'{self._ALL_CONFIRMATION_TEXT}' yaz."
                )

            if request.mode is MemoryForgetMode.CONFIRM_ALL:
                if not self._pending_clear_all:
                    return (
                        "Silme onayı bekleyen bir işlem yok."
                    )

                self._pending_clear_all = False
                removed = self._memory_service.clear_all()

                if not removed:
                    return (
                        "Uzun süreli hafızam zaten boş."
                    )

                return (
                    "Tüm uzun süreli hafıza kayıtlarını sildim. "
                    "Kalıcı profil bilgileri korunuyor."
                )

            if request.mode is MemoryForgetMode.CANCEL:
                if not self._pending_clear_all:
                    return None

                self._pending_clear_all = False
                return (
                    "Uzun süreli hafızayı silme işlemini iptal ettim."
                )

            self._pending_clear_all = False

            if request.mode is MemoryForgetMode.AMBIGUOUS:
                return (
                    "Hangi hafıza bilgisini silmem gerektiği net değil. "
                    "Örneğin 'Calculator API'nin test framework "
                    "bilgisini unut' şeklinde belirt."
                )

            if request.mode is MemoryForgetMode.LATEST:
                removed = self._memory_service.forget_latest()

                if removed is None:
                    return (
                        "Uzun süreli hafızamda silinecek kayıt yok."
                    )

                return (
                    "En son güncellenen hafıza kaydını unuttum: "
                    f"{removed.content}"
                )

            if request.mode is MemoryForgetMode.SUBJECT:
                if not request.subject:
                    return None

                removed = (
                    self._memory_service
                    .forget_subject(
                        subject=request.subject
                    )
                )

                if not removed:
                    return (
                        "Hafızamda bu konuya ait güvenilir "
                        "bir kayıt bulamadım."
                    )

                if len(removed) == 1:
                    return (
                        "Unuttum: "
                        f"{removed[0].content}"
                    )

                return (
                    f"{request.subject} ile ilgili "
                    f"{len(removed)} uzun süreli hafıza "
                    "kaydını unuttum."
                )

            if request.mode is MemoryForgetMode.TARGETED:
                if not request.subject or not request.relation:
                    return None

                removed = (
                    self._memory_service
                    .forget_structured(
                        subject=request.subject,
                        relation=request.relation,
                    )
                )

                if removed is None:
                    return (
                        "Hafızamda bu bilgiye ait güvenilir "
                        "bir kayıt bulamadım."
                    )

                return (
                    "Unuttum: "
                    f"{removed.content}"
                )

        return None