from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import re
import subprocess
import urllib.parse
import webbrowser
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Win32 Sanal Tuş Kodları (Ses Kontrolü)
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002

APP_COMMAND_MAP = {
    # Medya & Web Siteleri
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "spotify": "spotify:",
    "netflix": "https://www.netflix.com",
    "google": "https://www.google.com",
    "google.com": "https://www.google.com",
    "github": "https://www.github.com",
    "github.com": "https://www.github.com",
    "twitter": "https://www.x.com",
    "x": "https://www.x.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "discord": "discord:",
    "gmail": "https://mail.google.com",
    "ekşi": "https://eksisozluk.com",
    "ekşisözlük": "https://eksisozluk.com",
    "tarayıcı": "https://www.google.com",
    # Tarayıcılar
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    # Kod & Editör
    "vscode": "code",
    "vs code": "code",
    "kod editörü": "code",
    "not defteri": "notepad",
    "notepad": "notepad",
    # Sistem Araçları
    "hesap makinesi": "calc",
    "hesap": "calc",
    "calculator": "calc",
    "terminal": "powershell",
    "powershell": "powershell",
    "cmd": "cmd",
    "komut satırı": "cmd",
    "görev yöneticisi": "taskmgr",
    "task manager": "taskmgr",
    "dosya gezgini": "explorer",
    "dosyalar": "explorer",
    "belgelerim": "explorer",
    "ayarlar": "ms-settings:",
    "settings": "ms-settings:",
    "denetim masası": "control",
}


def open_application(app_name: str) -> Tuple[bool, str]:
    """İstenen uygulama veya web sitesini Windows üzerinde güvenle ve arka planda başlatır."""
    cleaned = app_name.lower().strip()
    cmd = APP_COMMAND_MAP.get(cleaned)

    # Eğer bir domain / URL ise (örn: youtube.com, google.com vb.)
    if not cmd and ("." in cleaned and not cleaned.endswith((".exe", ".bat", ".cmd", ".py"))):
        url = cleaned if cleaned.startswith(("http://", "https://")) else f"https://{cleaned}"
        try:
            webbrowser.open(url)
            return True, f"{cleaned} açıldı."
        except Exception as e:
            return False, f"{cleaned} açılamadı: {e}"

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        if cmd:
            if cmd.startswith(("http://", "https://")):
                webbrowser.open(cmd)
                display_name = "YouTube" if "youtube" in cleaned else app_name.capitalize()
                return True, f"{display_name} açıldı."
            if cmd.endswith(":"):
                os.startfile(cmd)
                return True, f"{app_name.capitalize()} açıldı."

            subprocess.Popen([cmd], shell=True, startupinfo=startupinfo, creationflags=creationflags)
            return True, f"{app_name.capitalize()} açıldı."
        else:
            # Doğrudan girilen program adını başlatmayı dene
            subprocess.Popen([cleaned], shell=True, startupinfo=startupinfo, creationflags=creationflags)
            return True, f"{app_name.capitalize()} başlatıldı."
    except Exception as e:
        logger.debug(f"Uygulama başlatma hatası ({app_name}): {e}")
        return False, f"{app_name} açılamadı: {e}"


def control_volume(action: str, steps: int = 5) -> Tuple[bool, str]:
    """Windows sistem ses seviyesini Win32 keybd_event API ile hassas ayarlar."""
    try:
        user32 = ctypes.windll.user32
        act = action.lower().strip()

        if act in ("up", "artır", "yükselt", "aç"):
            for _ in range(steps):
                user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                user32.keybd_event(VK_VOLUME_UP, 0, KEYEVENTF_KEYUP, 0)
            return True, "Ses seviyesi artırıldı."

        elif act in ("down", "azalt", "kıs", "alçalt"):
            for _ in range(steps):
                user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                user32.keybd_event(VK_VOLUME_DOWN, 0, KEYEVENTF_KEYUP, 0)
            return True, "Ses seviyesi kısıldı."

        elif act in ("mute", "sessiz", "kapat", "unmute"):
            user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_MUTE, 0, KEYEVENTF_KEYUP, 0)
            return True, "Ses sessize alındı / açıldı."

        return False, f"Bilinmeyen ses eylemi: {action}"
    except Exception as e:
        logger.debug(f"Ses kontrol hatası: {e}")
        return False, f"Ses kontrol edilemedi: {e}"


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def get_system_status() -> Tuple[bool, str]:
    """Pil, bellek ve sistem durumu hakkında anlık rapor üretir."""
    details = []
    try:
        # 1. Bellek Durumu
        mem = _MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            used_pct = mem.dwMemoryLoad
            total_gb = mem.ullTotalPhys / (1024 ** 3)
            avail_gb = mem.ullAvailPhys / (1024 ** 3)
            details.append(f"RAM: %{used_pct} kullanımda ({avail_gb:.1f} GB boş / {total_gb:.1f} GB toplam)")

        # 2. Pil Durumu
        power = _SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
            pct = power.BatteryLifePercent
            if pct != 255:
                state = "Prize Takılı (Şarj Oluyor)" if power.ACLineStatus == 1 else "Pilde Çalışıyor"
                details.append(f"Pil: %{pct} ({state})")

        if details:
            return True, "Sistem Durumu: " + " | ".join(details)
        return True, "Sistem normal çalışıyor."
    except Exception as e:
        logger.debug(f"Sistem durumu okuma hatası: {e}")
        return False, f"Sistem durumu alınamadı: {e}"


def search_web(query: str, platform: str = "google") -> Tuple[bool, str]:
    """Web veya YouTube üzerinde doğrudan arama açar."""
    try:
        encoded = urllib.parse.quote_plus(query.strip())
        if platform.lower() in ("youtube", "yt"):
            url = f"https://www.youtube.com/results?search_query={encoded}"
            webbrowser.open(url)
            return True, f"YouTube'da '{query}' için arama açıldı."
        else:
            url = f"https://www.google.com/search?q={encoded}"
            webbrowser.open(url)
            return True, f"Google'da '{query}' için arama açıldı."
    except Exception as e:
        return False, f"Arama açılamadı: {e}"


def resolve_system_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının Türkçe doğal dilde söylediği PC yönetim komutlarını çözer.
    Eğer sistem komutuyla eşleşirse işlemi yürütür ve söylenecek cevabı döndürür.
    Eşleşmezse None döner.
    """
    cleaned = user_text.lower().strip().strip(".!?,")

    # 1. Uygulama ve Web Sitelerini Açma Komutları ("... aç", "aç ...", "... başlat")
    # Örnek: "youtube aç", "youtube'u aç", "lütfen spotify aç", "aç youtube", "not defterini aç"
    target_cand = None
    open_suffix_match = re.match(r"^(?:lütfen\s+)?(.+?)\s+(?:aç|başlat|çalıştır)$", cleaned)
    open_prefix_match = re.match(r"^(?:aç|başlat|çalıştır)\s+(?:lütfen\s+)?(.+?)$", cleaned)

    if open_suffix_match:
        target_cand = open_suffix_match.group(1).strip()
    elif open_prefix_match:
        target_cand = open_prefix_match.group(1).strip()

    if target_cand:
        # Ekleri temizle (youtube'u -> youtube, spotify'ı -> spotify, not defterini -> not defteri)
        normalized = re.sub(r"'(?:[ıiuüae]|y[ıiuüae]|n[ıiuüae])?$", "", target_cand).strip()
        if normalized not in APP_COMMAND_MAP:
            # Türkçe tamlayan/iyelik eklerini ayıkla: not defterini -> not defteri, hesap makinesini -> hesap makinesi
            if normalized.endswith(("ini", "ını", "unu", "ünü")):
                cand = normalized[:-2]
                if cand in APP_COMMAND_MAP:
                    normalized = cand
            elif normalized.endswith(("i", "ı", "u", "ü", "yi", "yı", "yu", "yü")):
                cand = re.sub(r"(?:yi|yı|yu|yü|[ıiuü])$", "", normalized).strip()
                if cand in APP_COMMAND_MAP:
                    normalized = cand

        if normalized in APP_COMMAND_MAP or "." in normalized:
            ok, msg = open_application(normalized)
            return msg
        if target_cand in APP_COMMAND_MAP:
            ok, msg = open_application(target_cand)
            return msg

    # 2. Ses Kontrolü
    # Örnek: "sesi aç", "sesi yükselt", "sesi kıs", "sesi azalt", "sesi kapat", "sessize al"
    if re.search(r"\bses(?:i)?\s+(?:artır|yükselt|aç|fazlalaştır)\b", cleaned):
        _, msg = control_volume("up", steps=5)
        return msg
    if re.search(r"\bses(?:i)?\s+(?:kıs|azalt|alçalt|düşür)\b", cleaned):
        _, msg = control_volume("down", steps=5)
        return msg
    if re.search(r"\b(?:sesi kapat|sessize al|sesi kes)\b", cleaned):
        _, msg = control_volume("mute")
        return msg

    # 3. Sistem / Pil / Donanım Durumu
    # Örnek: "şarjım kaç", "pil durumu", "sistem durumu", "ram kullanımı", "bilgisayarın durumu"
    if any(k in cleaned for k in ("pil durumu", "şarjım kaç", "şarj ne kadar", "sistem durumu", "ram kullanımı", "donanım durumu", "bilgisayar durumu")):
        _, msg = get_system_status()
        return msg

    # 4. YouTube / Google Arama Komutları
    # Örnek: "youtube'da duman ara", "youtube aç duman", "google'da python nedir ara", "google'da ara python"
    yt_match = re.search(r"(?:youtube(?:'da|'de)?\s+(?:arama\s+yap|ara|çal|aç)\s*:?\s*|youtube'da\s+)(.+?)(?:\s+(?:ara|çal|aç))?$", cleaned)
    if yt_match and "youtube" in cleaned:
        query = yt_match.group(1).replace("youtube", "").strip()
        if query:
            _, msg = search_web(query, platform="youtube")
            return msg

    google_match = re.search(r"(?:google(?:'da|'de)?\s+(?:ara|arama yap)\s*:?\s*|google(?:'da|'de)?\s+)(.+?)(?:\s+(?:ara|arama yap))?$", cleaned)
    if google_match and "google" in cleaned:
        query = google_match.group(1).replace("google", "").strip()
        if query:
            _, msg = search_web(query, platform="google")
            return msg

    web_match = re.search(r"(?:internette|webde|internetten)\s+(?:ara|arama yap)\s*:?\s*(.+?)$", cleaned) or re.search(r"(?:internette|webde|internetten)\s+(.+?)\s+(?:ara|arama yap)$", cleaned)
    if web_match:
        query = web_match.group(1).strip()
        if query:
            _, msg = search_web(query, platform="google")
            return msg

    # 5. Ekran İnceleme / Görsel Zeka (Vision)
    # Örnek: "ekrana bak", "ekran görüntüsü al", "ekranı incele", "bu hataya bak", "ekranda ne var"
    if any(k in cleaned for k in ("ekrana bak", "ekranı incele", "ekran görüntüsü al", "ekran görüntüsünü incele", "ekranda ne var", "bu hataya bak")):
        try:
            from boru.tools.vision_tools import analyze_screen
            return analyze_screen(user_text)
        except Exception as e:
            return f"Ekran inceleme servisi çalıştırılamadı: {e}"

    return None
