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
    Yerel dil modelinin eski eğitim hafızasından uydurma yapmasını veya ezberden yanıt vermesini engeller.
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
        "bağımlılıklar:", "sembol ara:", "git ", "def ", "class ", "import "
    )

    _MEMORY_CHAT_REFERENCES = (
        "hatırla", "hatırlıyor musun", "az önce", "demin", "ne demiştim",
        "ne konuştuk", "benim adım", "adım ne", "beni tanıyor musun",
        "bahsettiğim", "söylediğim", "anlatayım mı", "sence", "fikrin ne",
        "fıkra anlat", "moralim bozuk", "canım sıkkın", "sohbet edelim"
    )

    def __init__(self, search_fn=None):
        self._search_fn = search_fn

    def build_context(self, user_message: str = "") -> str:
        text = user_message.strip()
        if not text or len(text) < 3:
            return ""

        cleaned = text.lower().strip(".!?, ")
        words = cleaned.split()

        # 1. Selamlaşma ve genel sohbet ifadelerini ele
        if len(words) <= 3 and any(w in self._GREETINGS for w in words):
            return ""

        # 2. Sistem komutlarını ve yerel aksiyonları ele
        if any(cmd in cleaned for cmd in self._SYSTEM_COMMANDS):
            return ""

        # 3. Konuşma geçmişi, hafıza ve kişisel dertleşme ifadelerini ele
        if any(ref in cleaned for ref in self._MEMORY_CHAT_REFERENCES):
            return ""

        # 4. Bilgi / Soru / Araştırma niyeti kontrolü
        has_info_intent = (
            "?" in text
            or any(w in cleaned for w in (
                "ne", "nedir", "kimdir", "nerede", "nerededir", "nasıl", "neden", "niçin",
                "kaç", "hangi", "ne zaman", "ne demek", "mı", "mi", "mu", "mü", "misin", "mısın"
            ))
            or any(kw in cleaned for kw in (
                "araştır", "araştırma", "bilgi", "hakkında", "ile ilgili", "tarihi", "fiyatı",
                "kur", "dolar", "euro", "altın", "borsa", "enflasyon", "asgari ücret", "faiz",
                "2024", "2025", "2026", "2027", "2028", "haber", "güncel", "son durum",
                "anlat", "açıkla", "özetle", "bakmam lazım", "öğrenmek istiyorum"
            ))
            or len(words) >= 4
        )

        if not has_info_intent:
            return ""

        # 5. Arama sorgusunu filtrele ve hazırla
        import re
        query = re.sub(r"^(?:börü\s+)?(?:lütfen\s+)?(?:bana\s+)?(?:senin\s+)?", "", text, flags=re.IGNORECASE).strip()
        query = re.sub(r"(?:bakmam\s+lazım|öğrenmek\s+istiyorum|merak\s+ettim|söyler\s+misin|bakar\s+mısın|bilgi\s+ver)[?.!]*$", "", query, flags=re.IGNORECASE).strip()
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
                    f"ÖNEMLİ TALİMAT: Kendi yerel model eğitim hafızandaki eski/tahmini bilgileri KESİNLİKLE KULLANMA. "
                    f"Yanıtını YALNIZCA yukarıdaki güncel ve güvenilir web araştırma sonuçlarına dayandır."
                )
            else:
                return (
                    f"[BİLGİ VE ARAŞTIRMA KISITI]\n"
                    f"Kullanıcının araştırılmasını istediği konu ('{query}') hakkında dış web kaynaklarından "
                    f"doğrulanmış bir veri henüz temin edilemedi.\n"
                    f"ÖNEMLİ KURAL: Kendi yerel model eğitim hafızandan ezberden bilgi uydurma veya eski verilerle tahmin yürütme. "
                    f"Kullanıcıya bu konuda doğrulanmış güncel bir araştırma verisi bulunamadığını dürüstçe belirt."
                )
        except Exception:
            pass

        return ""


class ActiveScreenContextProvider:
    """
    Ekrandaki aktif uygulama ve sayfa durumunu dil modeline aktaran bağlam sağlayıcı.
    Kullanıcı 'bu sayfada', 'burada', 'açılan sayfada' veya doğrudan medya/sayfa kontrolleri
    istediğinde modelin ekrandaki bağlamı bilmesini sağlar.
    """

    def __init__(self, screen_agent=None) -> None:
        self._screen_agent = screen_agent

    def build_context(self, user_message: str = "") -> str:
        agent = self._screen_agent
        if agent is None:
            try:
                from boru.tools.screen_agent import get_screen_agent
                agent = get_screen_agent()
            except Exception:
                return ""

        ctx = agent.get_active_context()
        if not ctx.app_name:
            return ""

        view_desc = {
            "playlists": "Çalma Listeleri Görünümü",
            "liked_songs": "Beğenilen Şarkılar",
            "search": "Arama Sonuçları",
            "video_player": "Video Oynatıcı",
            "file_view": "Klasör / Dosya Görünümü",
            "home": "Ana Sayfa / Başlangıç",
        }.get(ctx.current_view, ctx.current_view)

        return (
            f"[AKTİF EKRAN VE PENCERE BAĞLAMI]\n"
            f"Ön Plandaki Uygulama: {ctx.display_name} (Kategori: {ctx.category})\n"
            f"Aktif Sayfa/Görünüm: {view_desc}\n"
            f"Pencere Başlığı: {ctx.last_title or ctx.display_name}\n"
            f"Kullanıcı 'bu sayfada', 'burada', 'açılan sayfada' veya doğrudan oynatma/arama komutları verdiğinde "
            f"bu aktif ekranı temel alarak yanıt ver."
        )



