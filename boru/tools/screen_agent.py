"""
Börü Canlı Ekran & Sayfa Duyarlı Etkileşimli Bilgisayar Kontrol Ajanı (InteractiveScreenAgent).
========================================================================================
Kullanıcının Türkçe doğal dil ve sesle bilgisayarı kontrol ederken o an ekrandaki sayfayı /
uygulamayı göz önüne alarak ardışık ve akıllı işlem yapabilmesini sağlar:
- "Spotify aç" -> ardından "bu açılan sayfada çalma listemi aç"
- "ordan şu şarkıyı aç / çal" -> "müziği durdur" -> "sonraki şarkı"
- YouTube / Web: "bu sayfada Python ara" -> "videoyu durdur" -> "tam ekran yap"
- Tarayıcı & Gezinti: "sayfayı aşağı kaydır", "sayfayı yenile", "sekmeyi kapat", "yeni sekme aç"
- Ekran Durumu: "şu an ekranda ne açık?", "aktif pencere ne?", "ekrandaki sayfayı görüyor musun?"
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from datetime import datetime
import logging
import os
import re
import sys
import time
from typing import Optional, Tuple
import urllib.parse
import webbrowser

logger = logging.getLogger(__name__)

# Windows Sanal Tuş Kodları (Virtual Key Codes)
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22   # Page Down
VK_F5 = 0x74     # Refresh
VK_F11 = 0x7A    # Fullscreen
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_CONTROL = 0x11
KEYEVENTF_KEYUP = 0x0002


@dataclass
class ScreenAppContext:
    """Ekrandaki aktif uygulama ve sayfa bağlamını temsil eden veri modeli."""
    app_name: str = ""
    display_name: str = ""
    category: str = ""  # music, video, browser, editor, file_manager, system, general
    current_view: str = "home"  # home, playlists, liked_songs, search, video_player, file_view
    last_title: str = ""
    last_action: str = ""
    last_updated: float = 0.0

    def is_active(self, max_age_seconds: float = 900.0) -> bool:
        """Bağlamın hala geçerli ve güncel olup olmadığını belirler (varsayılan 15 dk)."""
        if not self.app_name:
            return False
        if self.last_updated <= 0:
            return True
        return (time.time() - self.last_updated) <= max_age_seconds


class InteractiveScreenAgent:
    """
    Ekrandaki aktif pencere ve sayfaları takip eden, sayfa-içi eylemleri
    doğrudan yerine getiren akıllı otonom ajan.
    """

    def __init__(self) -> None:
        self._current_context = ScreenAppContext()
        self._app_categories = {
            "spotify": ("Spotify", "music"),
            "youtube": ("YouTube", "video"),
            "youtube music": ("YouTube Music", "music"),
            "chrome": ("Google Chrome", "browser"),
            "edge": ("Microsoft Edge", "browser"),
            "firefox": ("Mozilla Firefox", "browser"),
            "tarayıcı": ("Web Tarayıcısı", "browser"),
            "vscode": ("Visual Studio Code", "editor"),
            "vs code": ("Visual Studio Code", "editor"),
            "kod editörü": ("Visual Studio Code", "editor"),
            "not defteri": ("Not Defteri", "editor"),
            "notepad": ("Not Defteri", "editor"),
            "dosya gezgini": ("Dosya Gezgini", "file_manager"),
            "explorer": ("Dosya Gezgini", "file_manager"),
            "indirilenler": ("İndirilenler Klasörü", "file_manager"),
            "masaüstü": ("Masaüstü Klasörü", "file_manager"),
            "belgeler": ("Belgeler Klasörü", "file_manager"),
            "terminal": ("Terminal", "system"),
            "powershell": ("PowerShell", "system"),
        }

    def update_active_app(
        self,
        app_name: str,
        display_name: str = "",
        category: str = "",
        current_view: str = "home",
        action: str = "opened",
        title: str = "",
    ) -> None:
        """Kullanıcı veya sistem tarafından bir uygulama açıldığında/değiştirildiğinde ekran bağlamını günceller."""
        cleaned = app_name.lower().strip()
        default_disp, default_cat = self._app_categories.get(cleaned, (app_name.capitalize(), "general"))

        final_disp = display_name or default_disp
        final_cat = category or default_cat

        self._current_context = ScreenAppContext(
            app_name=cleaned,
            display_name=final_disp,
            category=final_cat,
            current_view=current_view,
            last_title=title or final_disp,
            last_action=action,
            last_updated=time.time(),
        )
        logger.debug(f"Ekran bağlamı güncellendi: {self._current_context}")

    def get_active_context(self) -> ScreenAppContext:
        """Mevcut aktif ekran bağlamını döndürür. Eğer varsa Windows ön plan penceresini de yoklar."""
        fg_info = self._inspect_foreground_window()
        if fg_info:
            fg_title, fg_app = fg_info
            if fg_app:
                disp, cat = self._app_categories.get(fg_app, (fg_app.capitalize(), "general"))
                # Eğer son bağlamla uyumluysa veya yeni bir uygulama ön plana çıktıysa bağlamı tazele
                if not self._current_context.app_name or self._current_context.app_name != fg_app:
                    self._current_context = ScreenAppContext(
                        app_name=fg_app,
                        display_name=disp,
                        category=cat,
                        current_view="home",
                        last_title=fg_title,
                        last_action="focused",
                        last_updated=time.time(),
                    )
                else:
                    self._current_context.last_title = fg_title
        return self._current_context

    def _inspect_foreground_window(self) -> Optional[Tuple[str, str]]:
        """Windows API ile anlık ön plandaki aktif pencere başlığını ve olası uygulamasını tespit eder."""
        try:
            if sys.platform != "win32":
                return None
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return None

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return None

            lower_title = title.lower()
            detected_app = ""
            if "spotify" in lower_title:
                detected_app = "spotify"
            elif "youtube" in lower_title:
                detected_app = "youtube"
            elif "chrome" in lower_title:
                detected_app = "chrome"
            elif "edge" in lower_title:
                detected_app = "edge"
            elif "firefox" in lower_title:
                detected_app = "firefox"
            elif "visual studio code" in lower_title or "code" in lower_title:
                detected_app = "vscode"
            elif "not defteri" in lower_title or "notepad" in lower_title:
                detected_app = "notepad"
            elif any(k in lower_title for k in ("dosya gezgini", "indirilenler", "masaüstü", "belgeler")):
                detected_app = "explorer"

            return title, detected_app
        except Exception:
            return None

    # ── Spotify Sayfa İçi Eylemleri ──────────────────────────────────────────
    def open_spotify_playlists(self) -> Tuple[bool, str]:
        """Spotify üzerinde kullanıcının çalma listelerini ekranda açar."""
        self.update_active_app(
            "spotify",
            display_name="Spotify",
            category="music",
            current_view="playlists",
            action="opened_playlists",
        )
        try:
            os.startfile("spotify:collection:playlists")
            return True, "Spotify'da çalma listelerinizi açtım. Hangi parçayı veya listeyi oynatmamı istersiniz?"
        except Exception:
            try:
                webbrowser.open("https://open.spotify.com/collection/playlists")
                return True, "Spotify'da çalma listelerinizi açtım. Hangi parçayı veya listeyi oynatmamı istersiniz?"
            except Exception as e:
                return False, f"Çalma listesi açılamadı: {e}"

    def open_spotify_liked_songs(self) -> Tuple[bool, str]:
        """Spotify üzerinde 'Beğenilen Şarkılar' (Liked Songs) listesini açar."""
        self.update_active_app(
            "spotify",
            display_name="Spotify",
            category="music",
            current_view="liked_songs",
            action="opened_liked_songs",
        )
        try:
            os.startfile("spotify:collection:tracks")
            return True, "Spotify'da Beğenilen Şarkılar listenizi açtım. Hangi parçayı başlatayım?"
        except Exception:
            try:
                webbrowser.open("https://open.spotify.com/collection/tracks")
                return True, "Spotify'da Beğenilen Şarkılar listenizi açtım. Hangi parçayı başlatayım?"
            except Exception as e:
                return False, f"Beğenilen şarkılar açılamadı: {e}"

    def play_music_in_active_player(self, query: str) -> Tuple[bool, str]:
        """Ekrandaki aktif müzik uygulamasında (veya Spotify'da) istenen şarkıyı arayıp çalar."""
        cleaned = query.strip().strip("'").strip('"')
        if not cleaned:
            return False, "Çalınacak parça veya sanatçı belirtilmedi."

        # Ön ek temizleme
        clean_query = re.sub(
            r"^(?:işte\s+)?(?:şu\s+)?(?:şarkıyı|parçayı|müziği|albümü)\s*(?:aç|çal|dinlet|oynat)?\s*:?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        clean_query = re.sub(r"^(?:aç|çal|dinlet|oynat)\s*:?\s*", "", clean_query, flags=re.IGNORECASE).strip()
        clean_query = re.sub(r"\s+(?:şarkısı|parçası|müziği|çal|aç|dinlet)$", "", clean_query, flags=re.IGNORECASE).strip()
        if not clean_query:
            clean_query = cleaned

        self.update_active_app(
            "spotify",
            display_name="Spotify",
            category="music",
            current_view="search",
            action=f"playing_{clean_query}",
        )

        try:
            spotify_uri = f"spotify:search:{urllib.parse.quote(clean_query)}"
            try:
                os.startfile(spotify_uri)
                return True, f"Spotify'da '{clean_query}' aratıldı ve başlatıldı."
            except Exception:
                pass

            web_url = f"https://open.spotify.com/search/{urllib.parse.quote(clean_query)}"
            webbrowser.open(web_url)
            return True, f"Spotify'da '{clean_query}' açıldı."
        except Exception as e:
            return False, f"Müzik çalınamadı: {e}"

    # ── Donanım & Medya Tuş Kontrolleri ──────────────────────────────────────
    def send_media_key(self, action: str) -> Tuple[bool, str]:
        """Windows yerel ortam tuşlarıyla oynatma, durdurma ve parça geçişi yapar."""
        try:
            from boru.tools.system_tools import control_media
            return control_media(action)
        except Exception as e:
            return False, f"Medya komutu yürütülemedi: {e}"

    # ── Tarayıcı & Sayfa İçi Gezinti Eylemleri ────────────────────────────────
    def send_page_action(self, action: str) -> Tuple[bool, str]:
        """Aktif sayfada aşağı/yukarı kaydırma, yenileme, sekme kapatma ve tam ekran eylemleri."""
        try:
            user32 = ctypes.windll.user32 if sys.platform == "win32" else None
            if action == "scroll_down":
                if user32:
                    user32.keybd_event(VK_NEXT, 0, 0, 0)
                    user32.keybd_event(VK_NEXT, 0, KEYEVENTF_KEYUP, 0)
                return True, "Sayfa aşağı kaydırıldı."
            elif action == "scroll_up":
                if user32:
                    user32.keybd_event(VK_PRIOR, 0, 0, 0)
                    user32.keybd_event(VK_PRIOR, 0, KEYEVENTF_KEYUP, 0)
                return True, "Sayfa yukarı kaydırıldı."
            elif action == "fullscreen":
                if user32:
                    user32.keybd_event(VK_F11, 0, 0, 0)
                    user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)
                return True, "Tam ekran modu değiştirildi."
            elif action == "refresh":
                if user32:
                    user32.keybd_event(VK_F5, 0, 0, 0)
                    user32.keybd_event(VK_F5, 0, KEYEVENTF_KEYUP, 0)
                return True, "Sayfa yenilendi."
            elif action == "new_tab":
                if user32:
                    user32.keybd_event(VK_CONTROL, 0, 0, 0)
                    user32.keybd_event(ord('T'), 0, 0, 0)
                    user32.keybd_event(ord('T'), 0, KEYEVENTF_KEYUP, 0)
                    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                return True, "Yeni sekme açıldı."
            elif action == "close_tab":
                if user32:
                    user32.keybd_event(VK_CONTROL, 0, 0, 0)
                    user32.keybd_event(ord('W'), 0, 0, 0)
                    user32.keybd_event(ord('W'), 0, KEYEVENTF_KEYUP, 0)
                    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                return True, "Aktif sekme kapatıldı."
            return False, f"Tanınmayan sayfa eylemi: {action}"
        except Exception as e:
            return False, f"Sayfa komutu yürütülemedi: {e}"

    # ── Ekran ve Durum Raporu ────────────────────────────────────────────────
    def get_screen_summary(self) -> str:
        """Kullanıcıya o an ekranda neyin açık olduğunu ve ne komutlar verebileceğini açıklar."""
        ctx = self.get_active_context()
        if not ctx.app_name:
            return (
                "Şu an aktif bir ekran veya özel uygulama odağı seçili değil.\n"
                "Örneğin: 'Spotify aç', 'YouTube aç' veya 'Google aç' diyerek başlatabilirsiniz; "
                "ardından açılan sayfada doğrudan çalma listesi, arama veya medya kontrolleri yapabilirim."
            )

        view_desc = {
            "playlists": "Çalma Listeleri Görünümü",
            "liked_songs": "Beğenilen Şarkılar",
            "search": "Arama Sonuçları",
            "video_player": "Video Oynatıcı",
            "home": "Ana Sayfa",
        }.get(ctx.current_view, ctx.current_view)

        hints = []
        if ctx.category == "music":
            hints = [
                "• 'Şu şarkıyı çal: [şarkı adı]'",
                "• 'Müziği durdur' veya 'Devam ettir'",
                "• 'Sonraki şarkı' / 'Önceki şarkı'",
                "• 'Çalma listemi aç' veya 'Beğenilen şarkılarımı aç'",
            ]
        elif ctx.category in ("video", "browser"):
            hints = [
                "• 'Bu sayfada [konu] ara'",
                "• 'Videoyu durdur / oynat'",
                "• 'Tam ekran yap'",
                "• 'Sayfayı aşağı kaydır / yukarı kaydır'",
                "• 'Sayfayı yenile' veya 'Sekmeyi kapat'",
            ]
        else:
            hints = [
                "• 'Pencereyi kapat' veya 'Masaüstünü göster'",
                "• 'Ekran görüntüsü al'",
            ]

        hint_text = "\n".join(hints)
        return (
            f"📺 Aktif Ekran: {ctx.display_name} ({view_desc})\n"
            f"Son Durum / Pencere: {ctx.last_title or ctx.display_name}\n\n"
            f"Bu sayfada doğrudan söyleyebileceğiniz komutlar:\n{hint_text}"
        )


_SCREEN_AGENT_INSTANCE: Optional[InteractiveScreenAgent] = None


def get_screen_agent() -> InteractiveScreenAgent:
    """Tekil InteractiveScreenAgent örneğini döndürür."""
    global _SCREEN_AGENT_INSTANCE
    if _SCREEN_AGENT_INSTANCE is None:
        _SCREEN_AGENT_INSTANCE = InteractiveScreenAgent()
    return _SCREEN_AGENT_INSTANCE


def resolve_screen_agent_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının o anki ekrandaki sayfaya ve uygulamaya yönelik doğal dil
    ve sesli komutlarını çözer.
    """
    raw_text = user_text.strip().strip(".!?,")
    cleaned = raw_text.lower()
    agent = get_screen_agent()
    ctx = agent.get_active_context()

    # 1. Ekran Durumu Sorguları ("şu an ekranda ne açık?", "aktif sayfa ne?")
    if any(k in cleaned for k in (
        "ekranda ne var", "ekranda ne açık", "şu an ekranda ne var",
        "şu anda ekranda ne var", "aktif sayfa ne", "aktif pencere ne",
        "hangi penceredeyim", "ekrandaki sayfayı görüyor musun",
        "ekran durumu", "açık sayfayı göster", "bu ekranda ne var"
    )):
        return agent.get_screen_summary()

    # 2. Spotify Çalma Listesi & Beğenilen Şarkılar Komutları
    # Örnek: "bu açılan sayfada çalma listemi aç", "çalma listelerimi aç", "çalma listemi göster"
    is_playlist_query = any(k in cleaned for k in (
        "çalma listemi aç", "çalma listelerimi aç", "çalma listemi göster",
        "çalma listelerim", "çalma listelerimi göster", "playlist aç",
        "playlistlerimi aç", "çalma listeme git", "müzik listemi aç"
    ))
    if is_playlist_query:
        _, msg = agent.open_spotify_playlists()
        return msg

    # Örnek: "beğenilen şarkılarımı aç", "beğendiğim şarkılar", "favori şarkılarımı aç"
    is_liked_query = any(k in cleaned for k in (
        "beğenilen şarkılarımı aç", "beğendiğim şarkıları aç", "favori şarkılarımı aç",
        "beğenilenleri aç", "beğenilen şarkılar", "favorilerimi aç", "beğendiğim şarkılara git"
    ))
    if is_liked_query:
        _, msg = agent.open_spotify_liked_songs()
        return msg

    # 3. "Ordan müzik söylesem açsa" / "Ordan bir müzik aç/çal"
    if any(k in cleaned for k in (
        "ordan müzik söylesem", "ordan müzik aç", "ordan bir müzik aç",
        "ordan müzik çal", "ordan bir parça aç", "ordan bir şarkı çal",
        "açılan sayfadan müzik", "buradan müzik çal"
    )):
        return (
            "Elbette! Hangi şarkıyı veya sanatçıyı dinlemek istersiniz? "
            "Örneğin doğrudan 'Duman Koyu çal' veya 'Tarkan Kuzu Kuzu aç' diyebilirsiniz."
        )

    # 4. Medya & Oynatma Kontrolleri (Müziği durdur, devam ettir, sonraki şarkı vb.)
    # Play / Pause
    if any(k in cleaned for k in (
        "müziği durdur", "şarkıyı durdur", "müziği duraklat", "şarkıyı duraklat",
        "videoyu durdur", "videoyu duraklat", "durdur müziği", "şarkıyı durdur lütfen",
        "müziği durdurur musun"
    )):
        from boru.tools.system_tools import control_media
        _, msg = control_media("play_pause")
        return msg

    if any(k in cleaned for k in (
        "müziği devam ettir", "şarkıyı devam ettir", "müziği başlat", "şarkıyı başlat",
        "videoyu devam ettir", "videoyu başlat", "devam et", "devam ettir", "şarkıya devam et"
    )):
        from boru.tools.system_tools import control_media
        _, msg = control_media("play_pause")
        return msg

    # Next / Previous Track
    if any(k in cleaned for k in (
        "sonraki şarkı", "şarkıyı geç", "sonrakine geç", "sonraki parçaya geç",
        "sıradaki şarkı", "sonraki müzik", "diğer şarkıya geç", "şarkı atla"
    )):
        from boru.tools.system_tools import control_media
        _, msg = control_media("next")
        return msg

    if any(k in cleaned for k in (
        "önceki şarkı", "öncekine geç", "başa sar", "önceki parça", "önceki parçaya geç"
    )):
        from boru.tools.system_tools import control_media
        _, msg = control_media("prev")
        return msg

    # 5. Aktif Ekran Müzik Çalma ("ordan X çal", "bu sayfada X çal", "şu şarkıyı aç: X")
    # Eğer aktif uygulama müzik (Spotify) ise veya kullanıcı "ordan X çal", "bu sayfada X çal" diyorsa
    contextual_music_patterns = [
        r"^(?:bu\s+açılan\s+sayfada|açılan\s+sayfada|bu\s+sayfada|ordan|buradan)\s+(?:şu\s+)?(?:şarkıyı|parçayı|müziği\s+)?(.+?)\s+(?:çal|aç|oynat)$",
        r"^(?:ordan|buradan)\s+(.+?)\s+(?:çal|aç|oynat)$",
        r"^(?:şu\s+)?şarkıyı\s+(?:çal|aç)\s*:?\s*(.+)$",
        r"^şarkı\s+aç\s*:?\s*(.+)$",
    ]
    for pat in contextual_music_patterns:
        match = re.match(pat, raw_text, flags=re.IGNORECASE)
        if match:
            target = match.group(1).strip()
            if target.lower() not in ("aç", "çal", "müzik", "şarkı", "video", ""):
                _, msg = agent.play_music_in_active_player(target)
                return msg

    # Eğer aktif uygulama Spotify ise ve kullanıcı doğrudan "X çal" diyorsa ("Duman çal", "Mor ve Ötesi çal")
    if ctx.category == "music" or ctx.app_name == "spotify":
        quick_play_match = re.match(r"^(.+?)\s+(?:çal|dinlet)$", raw_text, flags=re.IGNORECASE)
        if quick_play_match:
            cand = quick_play_match.group(1).strip()
            # Genel sistem komutları ile çakışmayı önle
            if cand.lower() not in ("müzik", "şarkı", "ses", "gözcü", "yardım", ""):
                _, msg = agent.play_music_in_active_player(cand)
                return msg

    # 6. Tarayıcı & YouTube Sayfa İçi Eylemleri ("bu sayfada X ara", "videoyu durdur" vb.)
    search_in_page_match = re.match(
        r"^(?:bu\s+açılan\s+sayfada|açılan\s+sayfada|bu\s+sayfada|sayfada)\s+(.+?)\s+(?:ara|arat|bul)$",
        raw_text,
        flags=re.IGNORECASE,
    )
    if search_in_page_match:
        query = search_in_page_match.group(1).strip()
        if ctx.app_name == "youtube" or ctx.category == "video":
            encoded = urllib.parse.quote_plus(query)
            webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
            return f"YouTube sayfasında '{query}' aratıldı."
        else:
            encoded = urllib.parse.quote_plus(query)
            webbrowser.open(f"https://www.google.com/search?q={encoded}")
            return f"Sayfada '{query}' aratıldı."

    # Sayfa Gezinti & Tuş Eylemleri
    if any(k in cleaned for k in (
        "sayfayı aşağı kaydır", "aşağı kaydır", "aşağı in", "biraz aşağı kaydır", "aşağı kaydır lütfen"
    )):
        _, msg = agent.send_page_action("scroll_down")
        return msg

    if any(k in cleaned for k in (
        "sayfayı yukarı kaydır", "yukarı kaydır", "yukarı çık", "biraz yukarı kaydır", "yukarı kaydır lütfen"
    )):
        _, msg = agent.send_page_action("scroll_up")
        return msg

    if any(k in cleaned for k in ("tam ekran yap", "tam ekrana al", "tam ekran moduna geç", "tam ekrandan çık")):
        _, msg = agent.send_page_action("fullscreen")
        return msg

    if any(k in cleaned for k in ("sayfayı yenile", "bu sayfayı yenile", "sayfayı tekrar yükle", "yenile sayfayı")):
        _, msg = agent.send_page_action("refresh")
        return msg

    if any(k in cleaned for k in ("yeni sekme aç", "yeni sekme", "yeni bir sekme aç")):
        _, msg = agent.send_page_action("new_tab")
        return msg

    if any(k in cleaned for k in ("sekmeyi kapat", "bu sekmeyi kapat", "sayfayı kapat", "bu sayfayı kapat")):
        _, msg = agent.send_page_action("close_tab")
        return msg

    return None

