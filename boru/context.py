from collections.abc import Sequence

from boru.models import ChatMessage


class ConversationContextBuilder:
    """
    Kısa süreli konuşma geçmişinden modele gönderilecek
    context penceresini oluşturur.
    """

    MESSAGES_PER_TURN = 2

    def __init__(
        self,
        max_turns: int = 10,
        max_characters: int = 12_000,
        max_turn_characters: int | None = None,
    ):
        if max_turns < 1:
            raise ValueError("max_turns en az 1 olmalıdır.")

        if max_characters < 1:
            raise ValueError(
                "max_characters en az 1 olmalıdır."
            )

        self._max_turns = max_turns
        self._max_characters = max_characters
        if max_turn_characters is not None and max_turn_characters < 1:
            raise ValueError('max_turn_characters pozitif olmalıdır.')
        self._max_turn_characters = max_turn_characters

    def build(
        self,
        history: Sequence[ChatMessage],
    ) -> list[ChatMessage]:
        messages = list(history)

        if not messages:
            return []

        if len(messages) % self.MESSAGES_PER_TURN != 0:
            raise ValueError(
                "Konuşma geçmişi tamamlanmış "
                "user/assistant turlarından oluşmalıdır."
            )

        max_message_count = (
            self._max_turns
            * self.MESSAGES_PER_TURN
        )

        candidates = messages[-max_message_count:]

        selected_turns: list[list[ChatMessage]] = []
        used_characters = 0

        for index in range(
            len(candidates) - self.MESSAGES_PER_TURN,
            -1,
            -self.MESSAGES_PER_TURN,
        ):
            turn = candidates[
                index:index + self.MESSAGES_PER_TURN
            ]
            if self._max_turn_characters is not None:
                cap = min(self._max_turn_characters, max(2, self._max_characters // 2))
                turn = self._bounded_turn(turn, cap)

            turn_character_count = sum(
                len(message.content)
                for message in turn
            )

            if (
                selected_turns
                and used_characters + turn_character_count
                > self._max_characters
            ):
                break

            selected_turns.append(turn)
            used_characters += turn_character_count

            if used_characters >= self._max_characters:
                break

        selected_turns.reverse()

        return [
            message
            for turn in selected_turns
            for message in turn
        ]

    @staticmethod
    def _bounded_turn(turn, cap):
        if sum(len(m.content) for m in turn) <= cap:
            return turn
        result = []
        for message in turn:
            limit = cap // 2
            content = message.content
            if len(content) > limit:
                marker = '\n[bağlam kısaltıldı]\n'
                space = max(0, limit - len(marker))
                content = content[:space // 2] + marker + (content[-(space - space // 2):] if space else '')
            result.append(ChatMessage(message.role, content))
        return result


class SystemClockContextProvider:
    """Modele gerçek zamanlı sistem saati, günü ve yılını aktaran bağlam sağlayıcı."""

    _DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    _MONTHS = [
        "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
    ]

    def build_context(self, user_message: str = "") -> str:
        from datetime import datetime
        now = datetime.now()
        day_name = self._DAYS[now.weekday()]
        month_name = self._MONTHS[now.month]
        return (
            f"[GÜNCEL SİSTEM ZAMANI]: {now.day} {month_name} {now.year}, {day_name} "
            f"Saat {now.strftime('%H:%M')}. Geçerli takvim yılı {now.year}'dir. "
            f"Tarih, gün, ay veya yılla ilgili soruları bu gerçek zamanlı bilgiye göre yanıtla."
        )


class AutonomousWebGroundingContextProvider:
    """
    Kullanıcının dış dünya, güncel olaylar, olgusal bilgi veya araştırma gerektiren
    sorularında canlı internet / web araştırması yaparak doğrulanmış bilgiyi modele aktarır.
    Yerel dil modelinin eski eğitim verilerinden veya ezberinden uydurma yapmasını engeller.
    """

    _GREETINGS = {
        "selam", "merhaba", "günaydın", "iyi akşamlar", "iyi geceler", "nasılsın",
        "ne haber", "iyiyim", "sen nasılsın", "teşekkür", "teşekkürler", "sağ ol",
        "tamam", "olur", "evet", "hayır", "bakacağız", "anladım", "harika",
        "süper", "görüşürüz", "hoşça kal", "kolay gelsin"
    }

    _SYSTEM_COMMANDS = (
        "aç", "kapat", "sesi", "ses aç", "ses kıs", "sessize", "uygulama",
        "not defteri", "hesap makinesi", "terminal", "powershell", "masaüstü",
        "hafıza", "beni unut", "hatırla", "kodla:", "iyileştir:", "test:",
        "bağımlılıklar:", "git ", "def ", "class ", "import "
    )

    _RESEARCH_KEYWORDS = (
        "araştır", "araştırma", "web", "internet", "google", "bakmam lazım",
        "2024", "2025", "2026", "2027", "2028", "kimdir", "nedir", "nerede",
        "neresidir", "hangisidir", "kaç yılında", "ne zaman", "kaç para",
        "kaç tl", "ne kadar", "fiyatı", "ücreti", "enflasyon", "asgari ücret",
        "faiz", "borsa", "dolar", "euro", "altın", "togg", "seçim", "şampiyon",
        "haber", "nüfus", "hakkında bilgi", "ile ilgili bilgi", "neler oldu",
        "kim kazandı", "tarihi nedir", "son dakika", "güncel"
    )

    def __init__(self, search_fn=None):
        self._search_fn = search_fn

    def build_context(self, user_message: str = "") -> str:
        text = user_message.strip()
        if not text or len(text) < 3:
            return ""

        cleaned = text.lower().strip(".!?, ")

        # 1. Selamlaşma ve genel sohbet ifadelerini ele
        words = cleaned.split()
        if len(words) <= 3 and any(w in self._GREETINGS for w in words):
            return ""

        # 2. Sistem komutlarını ve yerel aksiyonları ele
        if any(cmd in cleaned for cmd in self._SYSTEM_COMMANDS):
            return ""

        # 3. Canlı bilgi / araştırma gerektiriyor mu kontrol et
        if not any(kw in cleaned for kw in self._RESEARCH_KEYWORDS):
            return ""

        # 4. Arama sorgusunu filtrele ve hazırla
        import re
        query = re.sub(r"^(?:börü\s+)?(?:lütfen\s+)?(?:bana\s+)?(?:senin\s+)?", "", text, flags=re.IGNORECASE).strip()
        query = re.sub(r"(?:bakmam\s+lazım|öğrenmek\s+istiyorum|merak\s+ettim|söyler\s+misin|bakar\s+mısın)[?.!]*$", "", query, flags=re.IGNORECASE).strip()
        if not query or len(query) < 3:
            query = text

        try:
            search_fn = self._search_fn
            if search_fn is None:
                from boru.tools.web_search import search_web_live
                search_fn = search_web_live

            ok, search_result = search_fn(query, max_results=2)
            if ok and search_result:
                return (
                    f"[GÜNCEL DOĞRULANMIŞ WEB VE ARAŞTIRMA VERİLERİ]\n"
                    f"Araştırma Konusu: {query}\n"
                    f"{search_result}\n"
                    f"ÖNEMLİ KURAL: Yanıtını kendi eski yerel model bilgine veya varsayımlarına göre DEĞİL, "
                    f"yukarıdaki güncel ve güvenilir web araştırma verilerine dayandırarak oluştur. "
                    f"Doğrulanmamış geçmiş bilgileri asla güncelmiş gibi sunma."
                )
        except Exception:
            pass

        return ""


