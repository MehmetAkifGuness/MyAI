"""
Börü Otonom Bilgisayar ve OS Kontrol Ajanı (AutonomousComputerAgent / OSController).
Kullanıcının Türkçe doğal dil ve sesli komutlarla bilgisayarı tam yetkiyle yönetmesini sağlar:
- Google, YouTube, Spotify ve programları açma
- Belirli YouTube videolarını arayıp doğrudan başlatma ("şu videoyu aç: X", "YouTube'da X aç")
- Spotify üzerinden müzik/şarkı arayıp çalma ("Spotify'da X çal", "şu şarkıyı aç: X")
- Windows klasörlerini açma (İndirilenler, Masaüstü, Belgeler, Proje dizini)
- Ekran görüntüsü alma ve kullanıcının resimler/masaüstü klasörüne kaydetme
- Ses, medya, görev ve sistem kontrolleri
- Tam erişimli otonom asistan rehberliği
"""

from __future__ import annotations

from datetime import datetime
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Optional, Tuple
import urllib.parse
import webbrowser

logger = logging.getLogger(__name__)

FOLDER_DISPLAY_NAMES = {
    "shell:Downloads": "İndirilenler",
    "shell:Desktop": "Masaüstü",
    "shell:Personal": "Belgeler",
    "shell:My Pictures": "Resimler",
    "shell:My Video": "Videolar",
    "shell:My Music": "Müzikler",
    ".": "Proje",
}


class AutonomousComputerAgent:
    """Windows işletim sistemini sözle ve doğal dille kontrol eden otonom ajan."""

    def __init__(self) -> None:
        self._folder_alias_map = {
            "indirilenler": "shell:Downloads",
            "indirilenler klasörü": "shell:Downloads",
            "indirilenleri": "shell:Downloads",
            "downloads": "shell:Downloads",
            "karşıdan yüklemeler": "shell:Downloads",
            "belgeler": "shell:Personal",
            "belgelerim": "shell:Personal",
            "belgeler klasörü": "shell:Personal",
            "documents": "shell:Personal",
            "masaüstü": "shell:Desktop",
            "masaüstünü": "shell:Desktop",
            "masaüstü klasörü": "shell:Desktop",
            "desktop": "shell:Desktop",
            "resimler": "shell:My Pictures",
            "resimlerim": "shell:My Pictures",
            "resimler klasörü": "shell:My Pictures",
            "fotoğraflar": "shell:My Pictures",
            "pictures": "shell:My Pictures",
            "videolar": "shell:My Video",
            "videolarım": "shell:My Video",
            "videolar klasörü": "shell:My Video",
            "videos": "shell:My Video",
            "müzikler": "shell:My Music",
            "müziklerim": "shell:My Music",
            "müziğim": "shell:My Music",
            "music": "shell:My Music",
            "proje": ".",
            "proje klasörü": ".",
            "çalışma dizini": ".",
            "çalışma klasörü": ".",
            "bu proje": ".",
        }

    def play_video(self, query_or_url: str) -> Tuple[bool, str]:
        """
        Belirtilen videoyu veya YouTube aramasını tarayıcıda hemen başlatır.
        URL veya doğal arama sorgusu alabilir.
        """
        cleaned = query_or_url.strip().strip("'").strip('"')
        if not cleaned:
            return False, "Oynatılacak video belirtilmedi."

        # Eğer doğrudan bir video URL'si ise
        if cleaned.startswith(("http://", "https://", "www.")) or "youtube.com" in cleaned or "youtu.be" in cleaned:
            url = cleaned if cleaned.startswith(("http://", "https://")) else f"https://{cleaned}"
            try:
                webbrowser.open(url)
                return True, f"Video doğrudan açıldı: {url}"
            except Exception as e:
                return False, f"Video linki açılamadı: {e}"

        # Arama terimindeki gereksiz dolguları ve önekleri temizle
        clean_query = re.sub(
            r"^(?:işte\s+)?(?:şu\s+)?(?:videoyu|video|klibi|kaydı)\s*(?:aç|oynat|izlet)?\s*:?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        clean_query = re.sub(
            r"^(?:aç|oynat|izlet)\s*:?\s*",
            "",
            clean_query,
            flags=re.IGNORECASE,
        ).strip()
        clean_query = re.sub(
            r"\s+(?:videosu|klibi|izle|oynat|aç)$",
            "",
            clean_query,
            flags=re.IGNORECASE,
        ).strip()
        if not clean_query:
            clean_query = cleaned

        try:
            encoded = urllib.parse.quote_plus(clean_query)
            target_url = f"https://www.youtube.com/results?search_query={encoded}"
            webbrowser.open(target_url)
            return True, f"YouTube'da '{clean_query}' videosu açıldı."
        except Exception as e:
            return False, f"Video aranamadı: {e}"

    def play_music(self, query: str, platform: str = "spotify") -> Tuple[bool, str]:
        """
        Spotify veya YouTube Music üzerinde müzik/şarkı arar ve çalar.
        """
        cleaned = query.strip().strip("'").strip('"')
        if not cleaned:
            return False, "Çalınacak şarkı veya sanatçı belirtilmedi."

        clean_query = re.sub(
            r"^(?:şu\s+)?(?:şarkıyı|parçayı|müziği|albümü)\s*(?:aç|çal|dinlet|oynat)?\s*:?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        clean_query = re.sub(
            r"^(?:aç|çal|dinlet|oynat)\s*:?\s*",
            "",
            clean_query,
            flags=re.IGNORECASE,
        ).strip()
        clean_query = re.sub(
            r"\s+(?:şarkısı|parçası|müziği|çal|aç|dinlet)$",
            "",
            clean_query,
            flags=re.IGNORECASE,
        ).strip()
        if not clean_query:
            clean_query = cleaned

        if platform.lower() == "spotify":
            try:
                # 1. Spotify yerel URI protokolü ile başlatmayı dene
                spotify_uri = f"spotify:search:{urllib.parse.quote(clean_query)}"
                try:
                    os.startfile(spotify_uri)
                    return True, f"Spotify'da '{clean_query}' aratıldı ve başlatıldı."
                except Exception:
                    pass

                # 2. Web Spotify fallback
                web_url = f"https://open.spotify.com/search/{urllib.parse.quote(clean_query)}"
                webbrowser.open(web_url)
                return True, f"Spotify'da '{clean_query}' açıldı."
            except Exception as e:
                return False, f"Spotify açılamadı: {e}"
        else:
            try:
                encoded = urllib.parse.quote_plus(clean_query)
                url = f"https://music.youtube.com/search?q={encoded}"
                webbrowser.open(url)
                return True, f"YouTube Music'te '{clean_query}' açıldı."
            except Exception as e:
                return False, f"Müzik açılamadı: {e}"

    def open_folder(self, folder_name_or_path: str) -> Tuple[bool, str]:
        """
        Windows üzerinde standart bir sistem klasörünü (İndirilenler, Masaüstü vb.)
        veya doğrudan bir dosya yolunu Gezginde açar.
        """
        cleaned = folder_name_or_path.lower().strip().strip("'").strip('"')
        normalized = re.sub(r"'(?:[ıiuüae]|y[ıiuüae]|n[ıiuüae])?$", "", cleaned).strip()
        if normalized.endswith(("ini", "ını", "unu", "ünü")):
            normalized = normalized[:-2]

        target_cmd = self._folder_alias_map.get(normalized) or self._folder_alias_map.get(cleaned)

        if not target_cmd:
            # Doğrudan sistem dosya yolu kontrolü
            if os.path.exists(folder_name_or_path):
                target_cmd = os.path.abspath(folder_name_or_path)
            elif os.path.exists(cleaned):
                target_cmd = os.path.abspath(cleaned)

        if not target_cmd:
            return False, f"'{folder_name_or_path}' klasörü bulunamadı."

        try:
            if target_cmd.startswith("shell:"):
                subprocess.Popen(["explorer.exe", target_cmd], shell=False)
                disp_name = FOLDER_DISPLAY_NAMES.get(target_cmd, normalized.capitalize())
                return True, f"{disp_name} klasörü açıldı."
            else:
                abs_path = os.path.abspath(target_cmd)
                if os.path.isdir(abs_path):
                    subprocess.Popen(["explorer.exe", abs_path], shell=False)
                    disp_name = FOLDER_DISPLAY_NAMES.get(target_cmd, "Klasör")
                    if disp_name != "Klasör":
                        return True, f"{disp_name} klasörü açıldı."
                    return True, f"Klasör açıldı: {abs_path}"
                else:
                    os.startfile(abs_path)
                    return True, f"Dosya açıldı: {abs_path}"
        except Exception as e:
            return False, f"Klasör açılamadı: {e}"

    def take_screenshot(self, target_dir: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mevcut ekranın yüksek çözünürlüklü ekran görüntüsünü alır ve
        kullanıcının Resimler veya Masaüstü klasörüne zaman damgalı PNG olarak kaydeder.
        """
        try:
            from PIL import ImageGrab

            home = os.path.expanduser("~")
            candidates = [
                target_dir,
                os.path.join(home, "Pictures", "Screenshots"),
                os.path.join(home, "Pictures"),
                os.path.join(home, "Desktop"),
            ]

            dest_dir = None
            for cand in candidates:
                if not cand:
                    continue
                try:
                    os.makedirs(cand, exist_ok=True)
                    if os.path.isdir(cand):
                        dest_dir = cand
                        break
                except Exception:
                    continue

            if not dest_dir:
                dest_dir = home

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Ekran_Goruntusu_{timestamp_str}.png"
            full_path = os.path.join(dest_dir, filename)

            try:
                img = ImageGrab.grab(all_screens=True)
            except Exception:
                img = ImageGrab.grab()

            img.save(full_path, format="PNG")
            return True, f"Ekran görüntüsü başarıyla alındı ve kaydedildi: {full_path}"
        except Exception as e:
            logger.debug(f"Ekran görüntüsü kaydetme hatası: {e}")
            return False, f"Ekran görüntüsü kaydedilemedi: {e}"

    def get_running_apps(self, limit: int = 5) -> Tuple[bool, str]:
        """Aktif çalışan ve en çok kaynak kullanan uygulamaları raporlar."""
        try:
            from boru.tools.system_tools import get_top_processes
            return get_top_processes(limit=limit)
        except Exception as e:
            return False, f"Çalışan uygulamalar listelenemedi: {e}"

    def get_agent_help_summary(self) -> str:
        """Kullanıcıya sözle / sesle bilgisayarda yapabileceği tüm eylemleri tanıtan zengin rehber."""
        return (
            "Börü Otonom Bilgisayar Ajanı Hazır!\n\n"
            "Bilgisayarınızı tamamen sözle ve doğal dille kontrol edebilirsiniz. İşte doğrudan söyleyebileceğiniz komut örnekleri:\n\n"
            "• Web & Video & Müzik:\n"
            "  - 'Google aç' veya 'YouTube aç'\n"
            "  - 'Şu videoyu aç: Python dersleri' veya 'YouTube'da Barış Manço aç'\n"
            "  - 'Spotify'da Duman çal' veya 'Şu şarkıyı aç: Tarkan Kuzu Kuzu'\n"
            "  - 'Müziği durdur' / 'Devam ettir' / 'Sonraki şarkı'\n\n"
            "• Klasör & Dosya Yönetimi:\n"
            "  - 'İndirilenler klasörünü aç'\n"
            "  - 'Masaüstünü aç' veya 'Belgelerimi aç'\n"
            "  - 'Resimler klasörünü aç' veya 'Proje klasörünü aç'\n\n"
            "• Uygulama & Donanım Denetimi:\n"
            "  - 'Chrome aç', 'Not defteri aç', 'VS Code aç', 'Hesap makinesi aç'\n"
            "  - 'Chrome'u kapat', 'Spotify'ı kapat'\n"
            "  - 'Sesi aç' / 'Sesi kıs' / 'Sesi kapat'\n"
            "  - 'Ekran görüntüsü al' (Resimlerinize anında PNG olarak kaydeder)\n"
            "  - 'Masaüstünü göster' / 'Pencereleri küçült'\n"
            "  - 'Hangi programlar açık?' veya 'Sistem durumu'\n"
            "  - 'Bilgisayarı kilitle' veya '30 dakika sonra bilgisayarı kapat'\n\n"
            "Ne yapmak isterseniz doğrudan söylemeniz yeterli, anında yerine getiririm!"
        )


_OS_AGENT_INSTANCE: Optional[AutonomousComputerAgent] = None


def get_autonomous_computer_agent() -> AutonomousComputerAgent:
    global _OS_AGENT_INSTANCE
    if _OS_AGENT_INSTANCE is None:
        _OS_AGENT_INSTANCE = AutonomousComputerAgent()
    return _OS_AGENT_INSTANCE


def resolve_os_controller_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının Türkçe doğal dildeki sesli / yazılı bilgisayar yönetim komutlarını çözer.
    Eğer tam erişimli otonom ajan eylemlerinden biriyle eşleşirse yürütür ve söylenecek cevabı döndürür.
    """
    raw_text = user_text.strip().strip(".!?,")
    cleaned = raw_text.lower()
    agent = get_autonomous_computer_agent()

    # 1. Otonom Ajan Rehberi & Sesle Kontrol Sorguları
    if any(k in cleaned for k in (
        "sözle kontrol", "sesle kontrol", "sözle yönet", "sesle yönet",
        "otonom bir ajan olsa", "otonom ajan mısın", "otonom ajan",
        "bilgisayarı kontrol edebilir misin", "bilgisayarı yönetebilir misin",
        "bilgisayarımda neler yapabilirsin", "bilgisayarda neler yapabilirsin",
        "bilgisayar ajanı"
    )):
        return agent.get_agent_help_summary()

    # 2. Belirli Video Açma Komutları
    video_patterns = [
        r"^(?:işte\s+)?(?:şu\s+)?(?:videoyu|video|klibi)\s+(?:aç|oynat|izlet)\s*:?\s*(.+)$",
        r"^(?:işte\s+)?(?:şu\s+)?video\s*:?\s*(.+)$",
        r"^youtube(?:'da|'de)\s+(?:şu\s+)?(?:videoyu\s+)?(.+?)\s+(?:aç|oynat|izlet|çalıştır)$",
        r"^youtube(?:'da|'de)\s+(.+?)\s+(?:videosunu\s+aç|videosu\s+aç|videosunu\s+oynat)$",
        r"^youtube(?:'da|'de)\s+(.+?)\s+(?:aç|oynat)$",
        r"^(.+?)\s+videosunu\s+(?:aç|oynat|izlet|başlat)$",
    ]
    for pattern in video_patterns:
        match = re.match(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            target = match.group(1).strip()
            if target.lower() in ("youtube", "video", "aç", "oynat", "izlet", ""):
                continue
            _, msg = agent.play_video(target)
            return msg

    # 3. Müzik & Spotify Özel Arama/Çalma Komutları
    music_patterns = [
        r"^spotify(?:'da|'de)\s+(?:şu\s+)?(?:şarkıyı|parçayı|müziği\s+)?(.+?)\s+(?:çal|aç|dinlet|oynat)$",
        r"^spotify(?:'da|'de)\s+(?:şu\s+)?(?:şarkıyı|parçayı|müziği\s+)?(.+)$",
        r"^(?:şu\s+)?(?:şarkıyı\s+aç|parçayı\s+aç|şarkıyı\s+çal|parçayı\s+çal)\s*:?\s*(.+)$",
        r"^(.+?)\s+şarkısını\s+(?:çal|aç|dinlet|oynat)$",
    ]
    for pattern in music_patterns:
        match = re.match(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            target = match.group(1).strip()
            if target.lower() in ("spotify", "müzik", "şarkı", "aç", "çal", "oynat", "başlat", ""):
                continue
            clean_target = re.sub(r"\s+(?:çal|aç|dinlet)$", "", target, flags=re.IGNORECASE).strip()
            _, msg = agent.play_music(clean_target, platform="spotify")
            return msg

    # 4. Klasör Açma Komutları
    folder_patterns = [
        r"^(?:lütfen\s+)?(.+?)\s+(?:klasörünü|klasörü|dizinini|dizini)\s+(?:aç|göster)$",
        r"^(?:aç|göster)\s+(?:lütfen\s+)?(.+?)\s+(?:klasörünü|klasörü|dizinini|dizini)$",
        r"^(?:lütfen\s+)?(indirilenler|indirilenleri|belgeler|belgelerim|masaüstü|resimler|videolar|müzikler|proje\s+klasörü|çalışma\s+dizini)\s+(?:aç|göster)$",
    ]
    for pattern in folder_patterns:
        match = re.match(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            target = match.group(1).strip()
            ok, msg = agent.open_folder(target)
            if ok:
                return msg

    # 5. Ekran Görüntüsü Alma & Kaydetme Komutları
    if any(k in cleaned for k in (
        "ekran görüntüsü al", "ekran görüntüsünü kaydet", "ekran görüntüsü kaydet",
        "ekranın resmini çek", "ekran resmi al", "ekran resmi kaydet", "screenshot al"
    )):
        _, msg = agent.take_screenshot()
        return msg

    # 6. Açık Programlar & Görev Takibi
    if any(k in cleaned for k in (
        "hangi programlar açık", "hangi uygulamalar açık", "çalışan programlar",
        "arka planda ne çalışıyor", "aktif programlar", "açık uygulamalar"
    )):
        _, msg = agent.get_running_apps()
        return msg

    return None
