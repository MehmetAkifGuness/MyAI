"""
boru.sentinel
=============
Börü Proaktif Arka Plan Bekçisi (Smart Watcher / Proactive Sentinel Service).
Arka planda sistem kaynaklarını ve süreçlerini gözlemler:
1. Uzun İşlem Gözcüsü (TaskCompletionWatcher): Terminalde çalışan pip, npm, cargo, docker, build vb. bittiğinde seslenir ("Güneş, npm install işlemi tamamlandı!").
2. Donanım & Pil Uyarısı: Pil %15'in altına düştüğünde ("Güneş, pil seviyeniz yüzde 14'e düştü. Bilgisayarı şarja takmanızı öneririm.").
3. Duruş & Mola Hatırlatıcısı: 1 saatlik kesintisiz çalışma sonrası ("Güneş, bir saattir ekrandasın. Bir bardak su alıp gözlerini dinlendirmek ister misin?").
4. Aşırı RAM Tüketim Uyarısı.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import subprocess
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

MONITORED_PROCESS_NAMES = {
    "pip.exe": "pip yükleme",
    "pip3.exe": "pip yükleme",
    "npm.cmd": "npm kurulum",
    "npm.exe": "npm kurulum",
    "npx.exe": "npx",
    "yarn.cmd": "yarn kurulum",
    "cargo.exe": "cargo derleme",
    "docker.exe": "docker",
    "cmake.exe": "cmake derleme",
    "msbuild.exe": "msbuild derleme",
    "pytest.exe": "pytest test",
}


def get_user_salutation() -> str:
    """Kullanıcıya hitap ederken ismini sezgisel hafızadan veya sistemden alır."""
    try:
        from boru.learning import get_implicit_learner
        learner = get_implicit_learner()
        profile = getattr(learner, "_profile", {})
        if "name" in profile and profile["name"]:
            return profile["name"]
    except Exception:
        pass
    return "Güneş"


class SentinelService:
    """
    Arka planda çalışan nöbetçi servis.
    Daemon thread olarak çalışır, ana uygulamayı asla bloke etmez.
    """

    def __init__(
        self,
        speak_fn: Optional[Callable[[str], None]] = None,
        check_interval_seconds: float = 10.0,
        enable_battery_sentinel: bool = True,
        enable_ram_sentinel: bool = True,
        enable_break_sentinel: bool = True,
        enable_task_sentinel: bool = True,
        break_interval_seconds: float = 3600.0,  # 1 saat
    ):
        self._speak_fn = speak_fn
        self._check_interval = check_interval_seconds
        self._enable_battery = enable_battery_sentinel
        self._enable_ram = enable_ram_sentinel
        self._enable_break = enable_break_sentinel
        self._enable_task = enable_task_sentinel

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Durum takibi
        self._low_battery_warned = False
        self._last_ram_warn_time = 0.0
        self._ram_warn_cooldown = 900.0  # 15 dakika
        self._start_time = time.time()
        self._last_break_warn_time = time.time()
        self._break_interval = break_interval_seconds

        # Aktif uzun işlem takibi (PID -> {"name": str, "first_seen": float})
        self._active_tasks: dict[int, dict] = {}
        self._min_task_duration = 6.0  # saniye

    def set_speak_fn(self, speak_fn: Callable[[str], None]) -> None:
        self._speak_fn = speak_fn

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def enable_battery(self) -> bool:
        return self._enable_battery

    @enable_battery.setter
    def enable_battery(self, val: bool) -> None:
        self._enable_battery = val

    @property
    def enable_ram(self) -> bool:
        return self._enable_ram

    @enable_ram.setter
    def enable_ram(self, val: bool) -> None:
        self._enable_ram = val

    @property
    def enable_break(self) -> bool:
        return self._enable_break

    @enable_break.setter
    def enable_break(self, val: bool) -> None:
        self._enable_break = val

    @property
    def enable_task(self) -> bool:
        return self._enable_task

    @enable_task.setter
    def enable_task(self, val: bool) -> None:
        self._enable_task = val

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="BoruSentinelLoop", daemon=True)
        self._thread.start()
        logger.info("Proaktif Akıllı Gözcü başlatıldı.")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("Proaktif Akıllı Gözcü durduruldu.")

    def _notify(self, message: str) -> None:
        logger.info(f"[Sentinel] {message}")
        if self._speak_fn is not None:
            try:
                self._speak_fn(message)
                return
            except Exception as e:
                logger.debug(f"Sentinel bildirim seslendirme hatası: {e}")

        # Eğer speak_fn atanmamışsa global speaker'ı dene
        try:
            from boru.voice.speaker import get_voice_output_service
            speaker = get_voice_output_service()
            speaker.speak(message, force=True)
        except Exception:
            pass

    def check_once(self) -> None:
        """Tek bir denetim adımı yürütür (testler ve periyodik çağrılar için)."""
        now = time.time()
        user_name = get_user_salutation()

        # 1. Pil Denetimi
        if self._enable_battery:
            try:
                import ctypes
                from ctypes import wintypes

                class _POWER(ctypes.Structure):
                    _fields_ = [
                        ("ACLineStatus", wintypes.BYTE),
                        ("BatteryFlag", wintypes.BYTE),
                        ("BatteryLifePercent", wintypes.BYTE),
                        ("SystemStatusFlag", wintypes.BYTE),
                        ("BatteryLifeTime", wintypes.DWORD),
                        ("BatteryFullLifeTime", wintypes.DWORD),
                    ]

                p = _POWER()
                if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p)):
                    pct = int(p.BatteryLifePercent)
                    unplugged = p.ACLineStatus == 0

                    if pct <= 15 and unplugged and pct != 255:
                        if not self._low_battery_warned:
                            self._low_battery_warned = True
                            self._notify(f"{user_name}, pil seviyeniz yüzde {pct}'e düştü. Bilgisayarı şarja takmanızı öneririm.")
                    elif p.ACLineStatus == 1 or pct > 20:
                        self._low_battery_warned = False
            except Exception as e:
                logger.debug(f"Sentinel pil denetim hatası: {e}")

        # 2. RAM Denetimi
        if self._enable_ram:
            try:
                import ctypes
                from ctypes import wintypes

                class _MEM(ctypes.Structure):
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

                m = _MEM()
                m.dwLength = ctypes.sizeof(_MEM)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                    load = m.dwMemoryLoad
                    if load >= 92 and (now - self._last_ram_warn_time > self._ram_warn_cooldown):
                        self._last_ram_warn_time = now
                        from boru.tools.system_tools import get_top_processes
                        _, top_msg = get_top_processes(limit=1)
                        self._notify(f"Dikkat: Bellek kullanımı yüzde {load}'a ulaştı. {top_msg}")
            except Exception as e:
                logger.debug(f"Sentinel RAM denetim hatası: {e}")

        # 3. Mola / Ergonomi Denetimi (1 Saat)
        if self._enable_break:
            if now - self._last_break_warn_time > self._break_interval:
                self._last_break_warn_time = now
                self._notify(f"{user_name}, bir saattir ekrandasın. Bir bardak su alıp gözlerini biraz dinlendirmek ister misin?")

        # 4. Uzun İşlem / Görev Tamamlanma Denetimi
        if self._enable_task:
            self._check_tasks(now, user_name)

    def _check_tasks(self, now: float, user_name: str) -> None:
        """Çalışan yükleme/derleme süreçlerini takip eder ve bitenler hakkında sesli haber verir."""
        try:
            current_pids: dict[int, str] = {}
            out = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                text=True,
                errors="ignore",
                timeout=3,
            )
            reader = csv.reader(io.StringIO(out))
            for row in reader:
                if len(row) >= 2 and row[1].strip().isdigit():
                    p_name = row[0].lower().strip()
                    p_id = int(row[1].strip())
                    if p_name in MONITORED_PROCESS_NAMES:
                        current_pids[p_id] = MONITORED_PROCESS_NAMES[p_name]

            # Biten işlemleri tespit et
            finished_pids = [pid for pid in self._active_tasks if pid not in current_pids]
            for pid in finished_pids:
                task = self._active_tasks.pop(pid)
                duration = now - task["first_seen"]
                if duration >= self._min_task_duration:
                    self._notify(f"{user_name}, {task['name']} işlemi tamamlandı!")

            # Yeni başlayan süreçleri kaydet
            for pid, name in current_pids.items():
                if pid not in self._active_tasks:
                    self._active_tasks[pid] = {"name": name, "first_seen": now}
        except Exception as e:
            logger.debug(f"Sentinel işlem takip hatası: {e}")

    def _loop(self) -> None:
        while self._running:
            self.check_once()
            for _ in range(int(self._check_interval * 2)):
                if not self._running:
                    break
                time.sleep(0.5)


# Global Singleton Instance
_GLOBAL_SENTINEL: Optional[SentinelService] = None


def get_sentinel() -> SentinelService:
    global _GLOBAL_SENTINEL
    if _GLOBAL_SENTINEL is None:
        _GLOBAL_SENTINEL = SentinelService()
    return _GLOBAL_SENTINEL


def resolve_sentinel_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının proaktif bekçi kontrollerini doğal dilde yönetmesini sağlar.
    Örnek: "proaktif uyarıları aç", "akıllı gözcüyü aç", "mola hatırlatıcısını aç", "bekçi durumu", "işlemler bitince haber ver"
    """
    cleaned = user_text.lower().strip().strip(".!?,")
    sentinel = get_sentinel()

    # 1. İşlem Tamamlanma Takibi
    if any(k in cleaned for k in (
        "işlem bitince haber ver", "işlemler bitince haber ver", "indirme bitince haber ver",
        "derleme bitince haber ver", "işlem takibini aç", "yükleme bitince seslen", "işlemleri izle"
    )):
        sentinel.enable_task = True
        if not sentinel.is_running:
            sentinel.start()
        return "İşlem gözcüsü aktif! Terminalde çalışan yükleme ve derleme işlemleri bittiğinde sesli olarak haber vereceğim."

    if any(k in cleaned for k in ("işlem takibini kapat", "işlem uyarısını kapat")):
        sentinel.enable_task = False
        return "Uzun işlem tamamlama uyarıları kapatıldı."

    # 2. Genel Proaktif Gözcü Açma / Kapatma
    if any(k in cleaned for k in (
        "proaktif uyarıları aç", "bekçiyi aç", "proaktif nöbetçiyi aç",
        "proaktif modu aç", "akıllı gözcüyü aç", "gözcüyü aç"
    )):
        sentinel.enable_battery = True
        sentinel.enable_ram = True
        sentinel.enable_break = True
        sentinel.enable_task = True
        if not sentinel.is_running:
            sentinel.start()
        return "Akıllı sistem gözcüsü aktif edildi! Pil <%15, 1 saatlik çalışma molası ve işlem tamamlama durumlarında sizi bilgilendireceğim."

    if any(k in cleaned for k in (
        "proaktif uyarıları kapat", "bekçiyi kapat", "proaktif nöbetçiyi kapat",
        "proaktif modu kapat", "akıllı gözcüyü kapat", "gözcüyü kapat"
    )):
        sentinel.enable_battery = False
        sentinel.enable_ram = False
        sentinel.enable_break = False
        sentinel.enable_task = False
        return "Akıllı sistem gözcüsü ve proaktif uyarılar kapatıldı."

    # 3. Mola Hatırlatıcı Açma / Kapatma
    if any(k in cleaned for k in ("mola hatırlatıcıyı aç", "mola hatırlatıcısını aç", "su molasını aç", "mola uyarısını aç")):
        sentinel.enable_break = True
        if not sentinel.is_running:
            sentinel.start()
        return "Mola ve ergonomi hatırlatıcısı açıldı. Her 1 saatte bir dinlenme ve su molası önereceğim."

    if any(k in cleaned for k in ("mola hatırlatıcıyı kapat", "mola hatırlatıcısını kapat", "su molasını kapat")):
        sentinel.enable_break = False
        return "Mola hatırlatıcısı kapatıldı."

    # 4. Gözcü Durumu
    if any(k in cleaned for k in ("bekçi durumu", "proaktif durum", "proaktif bekçi durumu", "gözcü durumu", "akıllı gözcü durumu")):
        st_bat = "Açık" if sentinel.enable_battery else "Kapalı"
        st_ram = "Açık" if sentinel.enable_ram else "Kapalı"
        st_brk = "Açık (1 saat)" if sentinel.enable_break else "Kapalı"
        st_tsk = "Açık" if sentinel.enable_task else "Kapalı"
        run_st = "Çalışıyor" if sentinel.is_running else "Durduruldu"
        return f"Akıllı Gözcü ({run_st}): Pil uyarısı: {st_bat}, RAM uyarısı: {st_ram}, Mola hatırlatıcı: {st_brk}, İşlem tamamlama: {st_tsk}."

    return None
