import re


class RuleBasedMemoryIntentDetector:
    """
    Bir mesajın kullanıcının kendi kalıcı
    bilgileriyle ilişkilendirilmesinin makul
    olup olmadığını belirler.

    Genel bilgi sorularında hafıza retrieval
    yapılmasını engeller.
    """

    _OWNED_TECHNICAL_SCOPE_PATTERN = re.compile(
        (
            r"\b("
            r"projem|projemde|projemin|projeme|projemden|"
            r"uygulamam|uygulamamda|uygulamamın|uygulamama|"
            r"servisim|servisimde|servisimin|servisime|"
            r"sistemim|sistemimde|sistemimin|sistemime|"
            r"kodum|kodumda|kodumun|koduma|"
            r"backendim|backendimde|backendimin|"
            r"frontendim|frontendimde|frontendimin|"
            r"veritabanım|veritabanımda|veritabanımın"
            r")\b"
        ),
        re.IGNORECASE,
    )

    _MEMORY_REFERENCE_PATTERN = re.compile(
        (
            r"\b("
            r"hafızanda|hafızandaki|hafızamda|"
            r"hatırlıyor\s+musun|hatırladığın|"
            r"daha\s+önce|önceden|"
            r"söylediğim|bahsettiğim|"
            r"kullandığım|seçtiğim|"
            r"kararlaştırdığım"
            r")\b"
        ),
        re.IGNORECASE,
    )

    _FIRST_PERSON_STATE_PATTERN = re.compile(
        (
            r"\b("
            r"kullanıyorum|kullanıyordum|kullanmıştım|"
            r"kullanıyor\s+muyum|"
            r"tercih\s+ediyorum|tercih\s+etmiştim|"
            r"seçmiştim|kurmuştum"
            r")\b"
        ),
        re.IGNORECASE,
    )

    def is_memory_relevant(
        self,
        user_message: str,
    ) -> bool:
        normalized = " ".join(
            user_message.strip().split()
        )

        if not normalized:
            return False

        return any(
            pattern.search(normalized)
            is not None
            for pattern in (
                self._OWNED_TECHNICAL_SCOPE_PATTERN,
                self._MEMORY_REFERENCE_PATTERN,
                self._FIRST_PERSON_STATE_PATTERN,
            )
        )