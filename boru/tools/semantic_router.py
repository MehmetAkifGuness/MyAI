"""
boru.tools.semantic_router
==========================
Doğal Türkçe, devrik cümleler, günlük konuşma dili ve esnek komutlar için
hibrit anlamsal niyet çözücü (Semantic Intent Resolver).

Katı regex sınırlarına takılmadan kullanıcının asıl niyetini ve parametrelerini
(süre, şarkı adı, şehir, eylem türü) çözer ve doğru araca yönlendirir.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SemanticIntentResolver:
    """
    Kullanıcının doğal dil isteklerini analiz edip niyetini ve parametrelerini
    çıkaran semantik yönlendirici.
    """

    @staticmethod
    def _clean_text(text: str) -> str:
        t = text.strip().lower().strip(".!?,:;")
        # Fazlalık nezaket ve dolgu sözcüklerini temizle
        noise_words = [
            "lütfen", "sana zahmet", "bi zahmet", "zahmet olmazsa",
            "hemen", "çabuk", "bi baksana", "baksana", "bakar mısın",
            "acaba", "hadi", "bana", "beni", "şuradan", "ordan", "buradan"
        ]
        for w in noise_words:
            t = re.sub(rf"\b{re.escape(w)}\b", "", t)
        return re.sub(r"\s+", " ", t).strip()

    # ── 0. Geri Bildirim, Eleştiri ve Hata Bildirimi Kalıpları ──────────────
    FEEDBACK_PATTERNS = [
        # Şarkı / Medya / Eylem başarısızlık bildirimleri
        r"\b(?:şarkı|müzik|parça|video|klip)?\s*(?:çalmadı|çalmıyor|çalamadın|çalmadın)\b",
        r"\b(?:şarkı|müzik|parça|video|klip|uygulama|sayfa|pencere)?\s*(?:açılmadı|açmadı|açmadın|açamadın|açılmıyor)\b",
        r"\b(?:çalışmadı|çalışmıyor|oynamadı|oynatmadı|oynatılmadı|başlamadı|başlatamadın)\b",
        r"\b(?:ses\s+(?:gelmiyor|çıkmıyor|yok))\b",
        # Yanlış anlama ve düzeltmeler
        r"\b(?:yanlış\s+(?:anladın|anlaşıldı|yaptın|açtın|çaldın|şarkı|müzik|cevap|şey|şeyi|parçayı|şarkıyı|yeri))\b",
        r"\b(?:hatalısın|hata\s+yaptın|hata\s+var|sorun\s+var|problem\s+var|bu\s+bir\s+(?:sorun|hata|problem))\b",
        r"\b(?:öyle\s+(?:değil|demedim|kastetmedim|istememiştim))\b",
        r"\b(?:tam\s+tersi|doğru\s+değil|alakasız|ne\s+alaka|alakası\s+yok)\b",
        # İstenmeyen arama / eylem şikayetleri
        r"\b(?:bunu\s+)?(?:sana\s+)?(?:aramam|araman|açman|çalman)\s+için\s+(?:söylemedim|demedim)\b",
        r"\b(?:bunu\s+)?(?:ara|arama\s+yap|arama)\s+demedim\b",
        r"\b(?:arama\s+(?:yapma|yapmanı\s+istemedim|istememiştim|yapmanı\s+söylemedim))\b",
        r"\b(?:bunu\s+)?(?:aç|çal|oynat)\s+demedim\b",
        r"\b(?:böyle\s+olsun\s+dememiştim|böyle\s+demedim|böyle\s+istememiştim)\b",
        r"\b(?:bunu\s+(?:kastetmedim|demedim|söylemedim|sormadım|istemedim))\b",
        r"\b(?:sana\s+bunu\s+(?:söylemedim|demedim|istememiştim))\b",
        r"\b(?:beceremedin|yapamadın|olmadı|başarısız\s+oldu)\b",
    ]

    @classmethod
    def resolve_feedback_intent(cls, text: str) -> Optional[str]:
        """
        Kullanıcının asistana yönelttiği hata bildirimlerini, eleştirileri veya
        düzeltmeleri ('şarkı çalmadı', 'yanlış anladın', 'bunu araman için söylemedim' vb.)
        tespit eder. Bu girdilerin ASLA bir arama terimi veya komut olarak algılanmasını engeller;
        durumu anlayan, hatayı kabul eden kibar ve net bir geri bildirim yanıtı üretir.
        """
        cleaned = text.strip().lower()
        is_feedback = any(re.search(p, cleaned, re.IGNORECASE) for p in cls.FEEDBACK_PATTERNS)
        if not is_feedback:
            return None

        # Özel durumlara göre kibar ve yapıcı yanıtlar
        if any(k in cleaned for k in ("çalmadı", "çalmıyor", "açılmadı", "çalışmadı", "ses gelmiyor", "ses çıkmıyor")):
            return (
                "Kusura bakmayın, işlem gerçekleşmemiş görünüyor. "
                "İlgili uygulama arka planda yanıt vermemiş veya parça başlatılamamış olabilir. "
                "Dilerseniz şarkıyı veya işlemi tekrar çalıştırmayı deneyebilirim; ne yapmamı istersiniz?"
            )
        elif any(k in cleaned for k in ("arama", "aramam", "araman", "arama yap")):
            return (
                "Anladım, kusura bakmayın. İfadenizi bir arama komutu olarak yanlış yorumladım. "
                "Geri bildiriminiz için teşekkürler; bu hatayı not aldım, arama yapmıyorum. Size nasıl yardımcı olabilirim?"
            )
        elif any(k in cleaned for k in ("yanlış", "hata", "öyle değil", "kastetmedim", "demedim")):
            return (
                "Kusura bakmayın, sizi yanlış anladım. Uyarınız için teşekkür ederim, hatamı kaydettim. "
                "Lütfen yapmak istediğiniz asıl işlemi belirtin, doğru şekilde yerine getireyim."
            )
        else:
            return (
                "Geri bildiriminiz için teşekkür ederim. İstenen sonucu doğru üretemediğimin farkındayım, "
                "hatamı not aldım. Size doğru şekilde yardımcı olabilmem için lütfen işlemi veya isteğinizi tekrar iletin."
            )

    @classmethod
    def sanitize_media_query(cls, text: str) -> str:
        """
        Kullanıcının müzik/şarkı arama talebindeki tüm dolgu kelimeleri, bağlaçları,
        emir eklerini ve önekleri temizleyerek saf arama terimini çıkarır.
        Örn: 'Ceza'dan Yerli Plaka şarkısını aç' -> 'Ceza Yerli Plaka'
        """
        cand = text.strip()
        # 1. Platform önekleri
        cand = re.sub(r"\b(?:spotify(?:'da|'de|da|de|'dan|'den|dan|den|'ı|'i|ı|i|'a|'e|a|e)?|youtube(?:'da|'de|da|de|'dan|'den|dan|den|'u|'a|'e|a|e)?)\b", "", cand, flags=re.IGNORECASE)
        # 2. Sanatçı ayrılma hali ekleri (Ceza'dan -> Ceza, Duman'dan -> Duman, Sezen Aksu'dan -> Sezen Aksu)
        cand = re.sub(r"'(?:dan|den|tan|ten)\b", "", cand, flags=re.IGNORECASE)
        cand = re.sub(r"\b([a-zA-ZçÇğĞıİöÖşŞüÜ]+)(?:dan|den|tan|ten)\b", r"\1", cand, flags=re.IGNORECASE)
        # 3. İyelik ve nesne ekleri: şarkısını, parçasını, müziğini vb.
        fillers = (
            "şarkısını", "şarkısı", "şarkı", "parçasını", "parçası", "parça",
            "müziğini", "müziği", "müzik", "klibini", "klibi", "klip",
            "albümünü", "albümü", "albüm", "videosunu", "videosu", "video"
        )
        for f in fillers:
            cand = re.sub(rf"\b{re.escape(f)}\b", "", cand, flags=re.IGNORECASE)
        # 4. Dolgu ve nezaket kelimeleri
        noise = (
            "lütfen", "bana", "bize", "bir", "şu", "hadi", "hemen", "zahmet olmazsa", "bi zahmet",
            "açsana", "çalsana", "oynatsana", "dinletsene", "başlatsana",
            "açabilir misin", "açar mısın", "açıver", "aç",
            "çalabilir misin", "çalar mısın", "çalıver", "çal",
            "oynat", "dinlet", "başlat"
        )
        for n in noise:
            cand = re.sub(rf"\b{re.escape(n)}\b", "", cand, flags=re.IGNORECASE)
        # 5. Fazlalık boşlukları temizle
        cand = re.sub(r"\s+", " ", cand).strip()
        return cand

    # ── 1. Hatırlatıcı ve Sayaç Niyeti ──────────────────────────────────────
    @classmethod
    def resolve_reminder(cls, text: str) -> Optional[Tuple[float, str]]:
        """
        'kahve için 15 dakika sayaç kurar mısın', 'yarım saat sonra uyar',
        '10 saniyelik sayaç başlat' gibi esnek cümleleri çözer.
        Döndürür: (süre_saniye, etiket)
        """
        cleaned = text.strip().lower()

        # Süre tespiti
        seconds = 0.0
        # Yarım saat / çeyrek saat
        if "yarım saat" in cleaned or "buçuk saat" in cleaned:
            seconds = 1800.0
        elif "çeyrek saat" in cleaned:
            seconds = 900.0
        else:
            # Saat
            hr_m = re.search(r"(\d+)\s*(?:saat|saatlik|st)\b", cleaned)
            if hr_m:
                seconds += float(hr_m.group(1)) * 3600.0

            # Dakika
            min_m = re.search(r"(\d+)\s*(?:dakika|dakikalık|dk)\b", cleaned)
            if min_m:
                seconds += float(min_m.group(1)) * 60.0

            # Saniye
            sec_m = re.search(r"(\d+)\s*(?:saniye|saniyelik|sn|san)\b", cleaned)
            if sec_m:
                seconds += float(sec_m.group(1))

        if seconds <= 0:
            return None

        # Niyet anahtar kelimeleri
        has_intent = any(k in cleaned for k in (
            "sayaç", "hatırlat", "uyar", "alarm", "zamanlayıcı",
            "kur", "başlat", "haber ver", "söyle", "de"
        ))
        if not has_intent:
            return None

        # Başlık/amaç çıkarma: 'kahve molası için 15 dakika...' -> 'Kahve molası'
        label = "Hatırlatıcı"
        clean_text = cls._clean_text(text)

        # 1. 'X için ...' kalıbı (için'den önceki kısım)
        pre_icin_match = re.search(r"^(.+?)\s+(?:için|diye|konusunda)\b", clean_text)
        if pre_icin_match:
            cand = pre_icin_match.group(1).strip()
            if cand and len(cand) > 1:
                label = cand.capitalize()
        else:
            # 2. '... diye uyar', '... de'
            post_match = re.search(r"(?:diye|şöyle)\s+(.+?)(?:uyar|de|hatırlat|$)", clean_text)
            if post_match:
                cand = post_match.group(1).strip()
                if cand and len(cand) > 1:
                    label = cand.capitalize()

        return seconds, label

    # ── 2. Müzik ve Medya Niyeti ─────────────────────────────────────────────
    @classmethod
    def resolve_media_action(cls, text: str) -> Optional[Tuple[str, Optional[str]]]:
        """
        'spotifydan duman açsana', 'şarkıyı durduruver', 'sonraki parçaya geç' gibi
        ifadeleri çözer.
        Döndürür: (eylem: 'play'|'pause'|'next'|'prev'|'playlists', hedef_parca)
        """
        # 1. Geri bildirim, eleştiri ve hata şikayetlerini asla müzik eylemi olarak algılama
        if cls.resolve_feedback_intent(text) is not None:
            return None

        cleaned = text.strip().lower()

        # 2. Olumsuz fiil denetimi (çalmadı, açılmadı, çalmıyor vb.)
        negative_verbs = (
            "çalmadı", "çalmıyor", "çalamadın", "çalmadın", "çalma",
            "açılmadı", "açmadı", "açmadın", "açamadın", "açılmıyor", "açma",
            "oynamadı", "oynatmadı", "oynatılmadı", "oynatma", "başlamadı",
        )
        if any(neg in cleaned for neg in negative_verbs):
            return None

        # Durdurma / Devam ettirme
        if any(k in cleaned for k in ("müziği durdur", "şarkıyı durdur", "müziği kes", "müziği kapat", "duraklat", "durduruver")):
            return "pause", None

        if any(k in cleaned for k in ("müziğe devam", "şarkıya devam", "devam ettir", "oynatmaya devam")):
            return "play", None

        # Sonraki / Önceki parça
        if any(k in cleaned for k in ("sonraki şarkı", "şarkıyı geç", "sonrakine geç", "sıradaki şarkı", "parçayı atla", "sonraki parçaya")):
            return "next", None

        if any(k in cleaned for k in ("önceki şarkı", "öncekine geç", "başa sar", "önceki parça")):
            return "prev", None

        # Çalma listesi
        if any(k in cleaned for k in ("çalma listemi aç", "çalma listelerimi", "playlist aç", "beğenilen şarkılarımı")):
            return "playlists", None

        # Müzik çalma talebi ('spotifydan Duman aç', 'bize bir Sezen Aksu çalsana', 'Ceza'dan Yerli Plaka şarkısını aç')
        play_verb_pattern = r"\b(?:çal|çalsana|çalar\s+mısın|aç|açsana|açar\s+mısın|oynat|dinlet|başlat)\b"
        has_play_verb = bool(re.search(play_verb_pattern, cleaned))
        music_context = any(k in cleaned for k in ("spotify", "müzik", "şarkı", "parça", "albüm"))

        if has_play_verb and music_context:
            sanitized = cls.sanitize_media_query(text)
            if sanitized and len(sanitized) > 1 and sanitized.lower() not in ("müzik", "şarkı", "spotify", "aç", "çal"):
                return "play_target", sanitized.title()

        return None

    # ── 3. Ekran ve Sayfa Durumu Niyeti ──────────────────────────────────────
    @classmethod
    def resolve_screen_intent(cls, text: str) -> Optional[str]:
        """
        'bi baksana şu an ekranda ne açık', 'ekranda hata var mı',
        'ekranı kontrol et' gibi durum sorgularını çözer.
        Döndürür: 'summary' veya 'analyze'
        """
        cleaned = text.strip().lower()

        if "ekran" in cleaned:
            if any(k in cleaned for k in ("hata", "detaylı analiz", "analiz", "resmini incele", "görsel analiz", "görsel incele")):
                return "analyze"
            if any(k in cleaned for k in (
                "ne var", "ne açık", "şu an", "sayfa", "aktif",
                "durumu", "görüyor musun", "bir bak", "baksana", "kontrol et"
            )):
                return "summary"

        return None

    # ── 4. Masaüstü Düzenleme Niyeti ─────────────────────────────────────────
    @classmethod
    def resolve_organizer_intent(cls, text: str) -> Optional[str]:
        """
        'masaüstünü toparlamadan önce göster', 'masaüstümü temizle',
        'düzenlemeyi geri al' gibi niyetleri çözer.
        Döndürür: 'preview', 'organize', 'undo'
        """
        cleaned = text.strip().lower()

        # Geri alma öncelikli kontrol edilir
        if any(k in cleaned for k in ("geri al", "geri getir", "eski haline")) and any(
            k in cleaned for k in ("düzenle", "masaüstü", "dosya", "işlem")
        ):
            return "undo"

        is_organize_req = any(k in cleaned for k in ("masaüstü", "desktop", "indirilenler")) and any(
            k in cleaned for k in ("düzenle", "toparla", "temizle", "organize et")
        )
        if is_organize_req:
            if any(k in cleaned for k in ("önce göster", "önizle", "önizleme", "önce bir göreyim", "bakayım", "toparlamadan önce")):
                return "preview"
            return "organize"

        return None

    # ── 5. Ana Çözücü Yönlendirme (Dispatch) ──────────────────────────────────
    @classmethod
    def resolve_and_execute(cls, user_text: str) -> Optional[str]:
        """
        Gelen metni anlamsal olarak analiz eder ve eşleşen bir niyet varsa
        doğrudan yürütüp yanıtını döndürür. Eşleşme yoksa None döner.
        """
        # 0. Öncelik: Geri Bildirim, Eleştiri ve Hata Bildirimi Niyeti
        # Kullanıcının şikayetlerini ve eleştirilerini asla komut/arama olarak işletme!
        fb_res = cls.resolve_feedback_intent(user_text)
        if fb_res is not None:
            return fb_res

        # 1. Hatırlatıcı / Sayaç
        rem_res = cls.resolve_reminder(user_text)
        if rem_res:
            secs, lbl = rem_res
            from boru.tools.reminder_tools import ReminderService
            svc = ReminderService.get_instance()
            _, msg = svc.schedule(secs, lbl)
            return msg

        # 2. Müzik ve Medya Eylemleri
        media_res = cls.resolve_media_action(user_text)
        if media_res:
            action, target = media_res
            from boru.tools.screen_agent import get_screen_agent
            agent = get_screen_agent()
            if action == "pause":
                _, msg = agent.send_media_key("play_pause")
                return "Müzik duraklatıldı."
            elif action == "play":
                _, msg = agent.send_media_key("play_pause")
                return "Müzik oynatılıyor."
            elif action == "next":
                _, msg = agent.send_media_key("next")
                return "Sonraki parçaya geçildi."
            elif action == "prev":
                _, msg = agent.send_media_key("prev")
                return "Önceki parçaya dönüldü."
            elif action == "playlists":
                _, msg = agent.open_spotify_playlists()
                return msg
            elif action == "play_target" and target:
                _, msg = agent.play_music_in_active_player(target)
                return msg

        # 3. Ekran Durumu & Analizi
        screen_res = cls.resolve_screen_intent(user_text)
        if screen_res == "summary":
            from boru.tools.screen_agent import get_screen_agent
            return get_screen_agent().get_screen_summary()
        elif screen_res == "analyze":
            from boru.tools.vision_tools import analyze_screen
            return analyze_screen()

        # 4. Masaüstü Düzenleme
        org_res = cls.resolve_organizer_intent(user_text)
        if org_res == "preview":
            from boru.tools.file_organizer import organize_desktop
            _, msg, _ = organize_desktop(preview=True)
            return msg
        elif org_res == "organize":
            from boru.tools.file_organizer import organize_desktop
            _, msg, _ = organize_desktop(preview=False)
            return msg
        elif org_res == "undo":
            from boru.tools.file_organizer import undo_organize_desktop
            _, msg = undo_organize_desktop()
            return msg

        return None
