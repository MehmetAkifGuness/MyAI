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
    "spotify": "spotify:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "tarayıcı": "https://www.google.com",
    "edge": "msedge",
    "vscode": "code",
    "vs code": "code",
    "kod editörü": "code",
    "not defteri": "notepad",
    "notepad": "notepad",
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
    """İstenen uygulamayı Windows üzerinde güvenle ve arka planda başlatır."""
    cleaned = app_name.lower().strip()
    cmd = APP_COMMAND_MAP.get(cleaned)

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        if cmd:
            if cmd.startswith(("http://", "https://")):
                webbrowser.open(cmd)
                return True, f"{app_name.capitalize()} açıldı."
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

    # 1. Uygulama Açma Komutları ("... aç", "... başlat")
    # Örnek: "spotify aç", "spotify'ı aç", "chrome'u başlat", "hesap makinesini aç"
    app_patterns = [
        r"^(?:lütfen\s+)?(spotify|chrome|google chrome|tarayıcı|edge|vscode|vs code|kod editörü|not defteri|notepad|hesap makinesi|hesap|calculator|terminal|powershell|cmd|görev yöneticisi|dosya gezgini|ayarlar|denetim masası)(?:'ı|'i|'u|'ü|'yi|'yı)?\s+(?:aç|başlat|çalıştır)$",
        r"^(?:aç|başlat|çalıştır)\s+(?:lütfen\s+)?(spotify|chrome|google chrome|tarayıcı|edge|vscode|vs code|kod editörü|not defteri|notepad|hesap makinesi|hesap|calculator|terminal|powershell|cmd|görev yöneticisi|dosya gezgini|ayarlar|denetim masası)$",
    ]
    for pattern in app_patterns:
        match = re.match(pattern, cleaned)
        if match:
            app_target = match.group(1)
            ok, msg = open_application(app_target)
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
    # Örnek: "youtube'da duman ara", "youtube aç duman", "google'da python nedir ara"
    yt_match = re.search(r"(?:youtube(?:'da|'de)?\s+(?:arama\s+yap|ara|çal|aç)\s*:?\s*|youtube'da\s+)(.+?)(?:\s+(?:ara|çal|aç))?$", cleaned)
    if yt_match and "youtube" in cleaned:
        query = yt_match.group(1).replace("youtube", "").strip()
        if query:
            _, msg = search_web(query, platform="youtube")
            return msg

    google_match = re.search(r"(?:google(?:'da|'de)?\s+(?:ara|arama yap)\s*:?\s*)(.+?)$", cleaned)
    if google_match:
        query = google_match.group(1).strip()
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
