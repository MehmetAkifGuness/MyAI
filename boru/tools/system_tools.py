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

# Win32 Sanal Tuş Kodları (Ses & Medya Kontrolü)
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_LWIN = 0x5B
VK_D = 0x44
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
    "belgeler": "explorer",
    "indirilenler": "explorer shell:Downloads",
    "downloads": "explorer shell:Downloads",
    "masaüstü": "explorer shell:Desktop",
    "resimler": "explorer shell:My Pictures",
    "ayarlar": "ms-settings:",
    "settings": "ms-settings:",
    "denetim masası": "control",
}

APP_PROCESS_MAP = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "msedge": "msedge.exe",
    "spotify": "Spotify.exe",
    "discord": "Discord.exe",
    "not defteri": "notepad.exe",
    "notepad": "notepad.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "kod editörü": "Code.exe",
    "hesap makinesi": "CalculatorApp.exe",
    "hesap": "CalculatorApp.exe",
    "calculator": "CalculatorApp.exe",
    "terminal": "powershell.exe",
    "powershell": "powershell.exe",
    "cmd": "cmd.exe",
    "görev yöneticisi": "Taskmgr.exe",
    "task manager": "Taskmgr.exe",
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
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008  # DETACHED_PROCESS

        if cmd:
            if cmd.startswith(("http://", "https://")):
                webbrowser.open(cmd)
                display_name = "YouTube" if "youtube" in cleaned else app_name.capitalize()
                return True, f"{display_name} açıldı."
            if cmd.endswith(":"):
                os.startfile(cmd)
                return True, f"{app_name.capitalize()} açıldı."

            # Windows ShellExecute (os.startfile) konsol açmadan yerel başlatır
            try:
                os.startfile(cmd)
                return True, f"{app_name.capitalize()} açıldı."
            except Exception:
                pass

            subprocess.Popen([cmd], shell=True, startupinfo=startupinfo, creationflags=creationflags, close_fds=True)
            return True, f"{app_name.capitalize()} açıldı."
        else:
            try:
                os.startfile(cleaned)
                return True, f"{app_name.capitalize()} başlatıldı."
            except Exception:
                pass
            subprocess.Popen([cleaned], shell=True, startupinfo=startupinfo, creationflags=creationflags, close_fds=True)
            return True, f"{app_name.capitalize()} başlatıldı."
    except Exception as e:
        logger.debug(f"Uygulama başlatma hatası ({app_name}): {e}")
        return False, f"{app_name} açılamadı: {e}"


def close_application(app_name: str) -> Tuple[bool, str]:
    """İstenen uygulamayı Windows üzerinde güvenle ve arka planda sonlandırır."""
    cleaned = app_name.lower().strip()
    normalized = re.sub(r"'(?:[ıiuüae]|y[ıiuüae]|n[ıiuüae])?$", "", cleaned).strip()
    if normalized not in APP_PROCESS_MAP:
        if normalized.endswith(("ini", "ını", "unu", "ünü")):
            cand = normalized[:-2]
            if cand in APP_PROCESS_MAP:
                normalized = cand
        elif normalized.endswith(("i", "ı", "u", "ü", "yi", "yı", "yu", "yü")):
            cand = re.sub(r"(?:yi|yı|yu|yü|[ıiuü])$", "", normalized).strip()
            if cand in APP_PROCESS_MAP:
                normalized = cand

    proc_name = APP_PROCESS_MAP.get(normalized)
    if not proc_name:
        proc_name = APP_PROCESS_MAP.get(cleaned)
    if not proc_name:
        if cleaned.endswith(".exe"):
            proc_name = cleaned
        else:
            proc_name = f"{cleaned}.exe"

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008

        res = subprocess.run(
            ["taskkill", "/F", "/IM", proc_name],
            startupinfo=startupinfo,
            creationflags=creationflags,
            capture_output=True,
            text=True,
            timeout=5,
        )
        display_name = normalized.capitalize() if normalized in APP_PROCESS_MAP else app_name.capitalize()
        if res.returncode == 0:
            return True, f"{display_name} kapatıldı."
        else:
            return False, f"{display_name} açık değil veya kapatılamadı."
    except Exception as e:
        logger.debug(f"Uygulama kapatma hatası ({app_name}): {e}")
        return False, f"{app_name} kapatılamadı: {e}"


def get_top_processes(limit: int = 3) -> Tuple[bool, str]:
    """En çok bellek tüketen aktif işlemleri tespit eder."""
    try:
        import csv
        import io
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008

        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            startupinfo=startupinfo,
            creationflags=creationflags,
            text=True,
            encoding="cp1254",
            errors="ignore",
            timeout=5,
        )
        reader = csv.reader(io.StringIO(out))
        procs: dict[str, int] = {}
        for row in reader:
            if len(row) >= 5:
                name = row[0]
                mem_str = row[4].replace(".", "").replace(" ", "").replace("K", "").replace("\xa0", "").strip()
                try:
                    mem_kb = int(mem_str)
                    procs[name] = procs.get(name, 0) + mem_kb
                except Exception:
                    pass
        if not procs:
            return False, "İşlem listesi alınamadı."

        sorted_procs = sorted(procs.items(), key=lambda x: x[1], reverse=True)[:limit]
        items = []
        for name, kb in sorted_procs:
            mb = kb / 1024
            items.append(f"{name} ({mb:.0f} MB)")

        msg = "En çok bellek kullanan uygulamalar: " + ", ".join(items) + "."
        return True, msg
    except Exception as e:
        logger.debug(f"İşlem listesi alma hatası: {e}")
        return False, f"İşlem listesi alınamadı: {e}"


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


def control_media(action: str) -> Tuple[bool, str]:
    """
    Windows üzerinde çalan medyayı (Spotify, YouTube, VLC vb.) küresel donanım medya tuşlarıyla yönetir.
    action: 'play_pause', 'next', 'prev', 'stop'
    """
    try:
        user32 = ctypes.windll.user32
        act = action.lower().strip()
        if act in ("play_pause", "play", "pause", "toggle", "oynat", "duraklat", "durdur"):
            user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, 0)
            return True, "Medya oynatıldı / duraklatıldı."
        elif act in ("next", "ileri", "sonraki", "geç"):
            user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, KEYEVENTF_KEYUP, 0)
            return True, "Sonraki parçaya geçildi."
        elif act in ("prev", "previous", "geri", "önceki"):
            user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, KEYEVENTF_KEYUP, 0)
            return True, "Önceki parçaya geçildi."
        elif act in ("stop", "tamamen durdur"):
            user32.keybd_event(VK_MEDIA_STOP, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_STOP, 0, KEYEVENTF_KEYUP, 0)
            return True, "Medya durduruldu."
        else:
            return False, f"Bilinmeyen medya eylemi: {action}"
    except Exception as e:
        logger.debug(f"Medya kontrol hatası: {e}")
        return False, f"Medya kontrol edilemedi: {e}"


def show_desktop() -> Tuple[bool, str]:
    """Tüm pencereleri küçülterek masaüstünü gösterir (Win+D)."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_LWIN, 0, 0, 0)
        user32.keybd_event(VK_D, 0, 0, 0)
        user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
        return True, "Masaüstü gösterildi."
    except Exception as e:
        logger.debug(f"Masaüstünü gösterme hatası: {e}")
        return False, f"Masaüstü gösterilemedi: {e}"


def lock_workstation() -> Tuple[bool, str]:
    """Windows oturumunu/ekranını kilitler (Win+L)."""
    try:
        ok = ctypes.windll.user32.LockWorkStation()
        if ok:
            return True, "Bilgisayar kilitlendi."
        return False, "Bilgisayar kilitlenemedi."
    except Exception as e:
        logger.debug(f"Kilitleme hatası: {e}")
        return False, f"Bilgisayar kilitlenemedi: {e}"


def schedule_shutdown(seconds: int, action: str = "shutdown") -> Tuple[bool, str]:
    """Bilgisayarı belirtilen süre sonra kapatılacak veya yeniden başlatılacak şekilde zamanlar."""
    try:
        flag = "/s" if action == "shutdown" else "/r"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(
            ["shutdown.exe", flag, "/t", str(seconds)],
            creationflags=creationflags,
            startupinfo=startupinfo,
            close_fds=True,
            check=True,
        )
        mins = seconds // 60
        act_name = "kapanacak" if action == "shutdown" else "yeniden başlayacak"
        dur_str = f"{mins} dakika" if mins > 0 else f"{seconds} saniye"
        return True, f"Bilgisayar {dur_str} sonra {act_name} şekilde ayarlandı."
    except Exception as e:
        logger.debug(f"Kapatma zamanlama hatası: {e}")
        return False, f"Kapatma zamanlanamadı: {e}"


def cancel_shutdown() -> Tuple[bool, str]:
    """Planlanmış bilgisayar kapatma/yeniden başlatma işlemini iptal eder."""
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(
            ["shutdown.exe", "/a"],
            creationflags=creationflags,
            startupinfo=startupinfo,
            close_fds=True,
            check=False,
        )
        return True, "Bilgisayarı kapatma işlemi iptal edildi."
    except Exception as e:
        logger.debug(f"Kapatma iptal hatası: {e}")
        return False, f"Kapatma iptal edilemedi: {e}"


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
    """İşlemci, bellek, disk ve pil durumu hakkında anlık rapor üretir."""
    details = []
    try:
        # 0. İşlemci (CPU) Kullanımı (GetSystemTimes ile 80ms ölçüm)
        try:
            import time

            class _FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", ctypes.c_uint), ("dwHighDateTime", ctypes.c_uint)]

            def _to_int(ft):
                return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

            i1, k1, u1 = _FILETIME(), _FILETIME(), _FILETIME()
            i2, k2, u2 = _FILETIME(), _FILETIME(), _FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i1), ctypes.byref(k1), ctypes.byref(u1))
            time.sleep(0.08)
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i2), ctypes.byref(k2), ctypes.byref(u2))
            idle_diff = _to_int(i2) - _to_int(i1)
            total_diff = (_to_int(k2) - _to_int(k1)) + (_to_int(u2) - _to_int(u1))
            if total_diff > 0:
                cpu_load = max(0.0, min(100.0, (1.0 - (idle_diff / total_diff)) * 100.0))
                details.append(f"İşlemci (CPU): %{cpu_load:.0f} kullanımda")
        except Exception:
            pass

        # 1. Bellek Durumu
        mem = _MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            used_pct = mem.dwMemoryLoad
            total_gb = mem.ullTotalPhys / (1024 ** 3)
            avail_gb = mem.ullAvailPhys / (1024 ** 3)
            details.append(f"RAM: %{used_pct} kullanımda ({avail_gb:.1f} GB boş / {total_gb:.1f} GB toplam)")

        # 2. Disk Durumu (C:\)
        try:
            free_bytes = ctypes.c_ulonglong()
            total_bytes = ctypes.c_ulonglong()
            total_free = ctypes.c_ulonglong()
            if ctypes.windll.kernel32.GetDiskFreeSpaceExW("C:\\", ctypes.byref(free_bytes), ctypes.byref(total_bytes), ctypes.byref(total_free)):
                c_free_gb = free_bytes.value / (1024 ** 3)
                c_total_gb = total_bytes.value / (1024 ** 3)
                details.append(f"Disk (C:): {c_free_gb:.1f} GB boş / {c_total_gb:.1f} GB toplam")
        except Exception:
            pass

        # 3. Pil Durumu
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

    # 0. Günlük Brifing (Jarvis Briefing)
    try:
        from boru.tools.briefing_tools import resolve_briefing_command
        brf_res = resolve_briefing_command(user_text)
        if brf_res is not None:
            return brf_res
    except Exception as e:
        logger.debug(f"Brifing çözme hatası: {e}")

    # 0.1 Proaktif Arka Plan Bekçisi
    try:
        from boru.sentinel import resolve_sentinel_command
        sent_res = resolve_sentinel_command(user_text)
        if sent_res is not None:
            return sent_res
    except Exception as e:
        logger.debug(f"Sentinel çözme hatası: {e}")

    # 0.2 Canlı Web Bilgi & Ansiklopedi Motoru (Wikipedia / Kimdir / Nedir)
    try:
        from boru.tools.web_qa_tools import resolve_web_qa_command
        qa_res = resolve_web_qa_command(user_text)
        if qa_res is not None:
            return qa_res
    except Exception as e:
        logger.debug(f"Web QA çözme hatası: {e}")

    # 0.3 Akıllı Masaüstü & Dosya Düzenleyici
    try:
        from boru.tools.file_organizer import resolve_file_organizer_command
        file_res = resolve_file_organizer_command(user_text)
        if file_res is not None:
            return file_res
    except Exception as e:
        logger.debug(f"Dosya düzenleyici çözme hatası: {e}")

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

    # 1.1 Uygulama Kapatma Komutları ("... kapat", "kapat ...", "... sonlandır")
    # Örnek: "chrome'u kapat", "not defterini kapat", "spotify'ı kapat", "kapat vscode", "discord sonlandır"
    close_suffix = re.match(r"^(?:lütfen\s+)?(.+?)\s+(?:kapat|sonlandır|durdur)$", cleaned)
    close_prefix = re.match(r"^(?:kapat|sonlandır|durdur)\s+(?:lütfen\s+)?(.+?)$", cleaned)
    close_cand = None
    if close_suffix:
        close_cand = close_suffix.group(1).strip()
    elif close_prefix:
        close_cand = close_prefix.group(1).strip()

    if close_cand and not any(k in close_cand for k in ("bilgisayar", "pc", "ekran", "müzik", "şarkı", "kapatmayı", "kapanma", "oturumu", "ses")):
        norm_cand = re.sub(r"'(?:[ıiuüae]|y[ıiuüae]|n[ıiuüae])?$", "", close_cand).strip()
        if norm_cand.endswith(("ini", "ını", "unu", "ünü")):
            norm_cand = norm_cand[:-2]
        elif norm_cand.endswith(("i", "ı", "u", "ü", "yi", "yı", "yu", "yü")):
            norm_cand = re.sub(r"(?:yi|yı|yu|yü|[ıiuü])$", "", norm_cand).strip()

        if norm_cand in APP_PROCESS_MAP or close_cand in APP_PROCESS_MAP or norm_cand.endswith(".exe"):
            _, msg = close_application(norm_cand)
            return msg

    # 2. Medya & Müzik Kontrolü (Spotify, YouTube, VLC vb.)
    # Örnek: "müziği durdur", "şarkıyı duraklat", "devam ettir", "müziği çal", "sonraki şarkı", "şarkıyı geç", "önceki parça"
    if re.search(r"\b(?:müziği|şarkıyı|parçayı|medyayı)?\s*(?:durdur|duraklat|pause)\b", cleaned) and "uygulama" not in cleaned:
        _, msg = control_media("play_pause")
        return msg
    if re.search(r"\b(?:müziği|şarkıyı|parçayı|medyayı)?\s*(?:devam ettir|sürdür|çal|oynat)\b", cleaned) and "aç" not in cleaned and "uygulama" not in cleaned:
        _, msg = control_media("play_pause")
        return msg
    if re.search(r"\b(?:sonraki|sıradaki|ileri)\s+(?:şarkı|parça|müzik|video)\b|\bşarkıyı\s+geç\b", cleaned):
        _, msg = control_media("next")
        return msg
    if re.search(r"\b(?:önceki|geçen|geri)\s+(?:şarkı|parça|müzik|video)\b|\bbaşa\s+sar\b", cleaned):
        _, msg = control_media("prev")
        return msg

    # 3. Ses Kontrolü
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

    # 3.1 Sistem / RAM / Pil / Donanım Durumu
    # Örnek: "hangi program çok ram yiyor", "en çok bellek harcayanlar"
    if any(k in cleaned for k in ("hangi program çok ram", "en çok bellek", "en çok ram", "belleği kim kullanıyor", "ram sömüren", "en çok kaynak")):
        _, msg = get_top_processes()
        return msg

    # Örnek: "şarjım kaç", "pil durumu", "sistem durumu", "ram kullanımı", "ram durumu", "bellek durumu", "donanım durumu", "işlemci kullanımı", "cpu durumu", "disk durumu"
    if any(k in cleaned for k in (
        "pil durumu", "şarjım kaç", "şarj ne kadar", "sistem durumu",
        "ram kullanımı", "ram durumu", "bellek durumu", "donanım durumu",
        "bilgisayar durumu", "ne kadar ram", "cpu durumu", "cpu kullanımı",
        "işlemci kullanımı", "işlemci durumu", "disk durumu", "depolama durumu",
        "harddisk", "bilgisayarın durumu"
    )):
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

    # 4. Canlı Web Araması & Haberler (Tarayıcı açmadan doğrudan sesli/metin özet)
    try:
        from boru.tools.web_search import resolve_web_search_command
        live_search_res = resolve_web_search_command(user_text)
        if live_search_res is not None:
            return live_search_res
    except Exception as e:
        logger.debug(f"Canlı web arama hatası: {e}")

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

    # 6. Canlı Hızlı Bilgi (Hava Durumu, Dolar, Euro vb. - Tarayıcı açmadan anında sesli cevap)
    try:
        from boru.tools.quick_info import resolve_quick_info
        quick_res = resolve_quick_info(user_text)
        if quick_res is not None:
            return quick_res
    except Exception as e:
        logger.debug(f"Hızlı bilgi çözme hatası: {e}")

    # 7. Akıllı Sayaç & Hatırlatıcı
    try:
        from boru.tools.reminder_tools import resolve_reminder_command
        reminder_res = resolve_reminder_command(user_text)
        if reminder_res is not None:
            return reminder_res
    except Exception as e:
        logger.debug(f"Hatırlatıcı çözme hatası: {e}")

    # 8. Pano (Clipboard) Asistanı
    try:
        from boru.tools.clipboard_tools import resolve_clipboard_command
        clip_res = resolve_clipboard_command(user_text)
        if clip_res is not None:
            return clip_res
    except Exception as e:
        logger.debug(f"Pano çözme hatası: {e}")

    # 9. Sesli Hızlı Not Defteri
    try:
        from boru.tools.notes_tools import resolve_notes_command
        notes_res = resolve_notes_command(user_text)
        if notes_res is not None:
            return notes_res
    except Exception as e:
        logger.debug(f"Not defteri çözme hatası: {e}")

    # 10. Windows Masaüstü & Güç Makroları
    if any(k in cleaned for k in ("masaüstünü göster", "masaüstüne dön", "pencereleri küçült", "masaüstünü aç")):
        _, msg = show_desktop()
        return msg

    if any(k in cleaned for k in ("bilgisayarı kilitle", "bilgisayarı kitle", "ekranı kilitle", "oturumu kilitle")):
        _, msg = lock_workstation()
        return msg

    if any(k in cleaned for k in ("kapatmayı iptal et", "kapatmayı durdur", "kapatma iptal", "kapanmayı iptal et")):
        _, msg = cancel_shutdown()
        return msg

    shutdown_match = re.search(r"^(?:(\d+)\s*(dakika|saat|sn|saniye)\s+sonra\s+)?bilgisayarı\s+(kapat|yeniden başlat)(?:\s+(\d+)\s*(dakika|saat|sn|saniye)\s+sonra)?$", cleaned)
    if shutdown_match:
        p1_val, p1_u, act, p2_val, p2_u = shutdown_match.groups()
        dur_val = p1_val or p2_val
        dur_u = p1_u or p2_u
        secs = 60
        if dur_val:
            v = int(dur_val)
            if dur_u in ("dakika", "dk"):
                secs = v * 60
            elif dur_u in ("saat",):
                secs = v * 3600
            else:
                secs = v

        action_type = "restart" if "yeniden" in act else "shutdown"
        _, msg = schedule_shutdown(secs, action=action_type)
        return msg

    return None
