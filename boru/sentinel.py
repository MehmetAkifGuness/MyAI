"""
boru.sentinel
=============
Börü Proaktif Arka Plan Bekçisi (Proactive Sentinel Service).
Arka planda sistem kaynaklarını (düşük pil, aşırı RAM kullanımı ve ergonomi/mola süreleri)
periyodik olarak gözlemler; kritik eşiklerde kullanıcıyı sesli veya görsel olarak uyarır.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class SentinelService:
    """
    Arka planda çalışan nöbetçi servis.
    Daemon thread olarak çalışır, ana uygulamayı asla bloke etmez.
    """

    def __init__(
        self,
        speak_fn: Optional[Callable[[str], None]] = None,
        check_interval_seconds: float = 30.0,
        enable_battery_sentinel: bool = True,
        enable_ram_sentinel: bool = True,
        enable_break_sentinel: bool = False,
    ):
        self._speak_fn = speak_fn
        self._check_interval = check_interval_seconds
        self._enable_battery = enable_battery_sentinel
        self._enable_ram = enable_ram_sentinel
        self._enable_break = enable_break_sentinel

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Durum takibi
        self._low_battery_warned = False
        self._last_ram_warn_time = 0.0
        self._ram_warn_cooldown = 900.0  # 15 dakika
        self._start_time = time.time()
        self._last_break_warn_time = time.time()
        self._break_interval = 5400.0  # 90 dakika

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

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="BoruSentinelLoop", daemon=True)
        self._thread.start()
        logger.info("Proaktif Arka Plan Bekçisi başlatıldı.")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("Proaktif Arka Plan Bekçisi durduruldu.")

    def _notify(self, message: str) -> None:
        logger.info(f"[Sentinel] {message}")
        if self._speak_fn is not None:
            try:
                self._speak_fn(message)
            except Exception as e:
                logger.debug(f"Sentinel bildirim seslendirme hatası: {e}")

    def check_once(self) -> None:
        """Tek bir denetim adımı yürütür (testler ve periyodik çağrılar için)."""
        now = time.time()

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
                            self._notify(f"Efendim, pil seviyeniz yüzde {pct}'e düştü. Bilgisayarı şarja takmanızı öneririm.")
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

        # 3. Mola / Ergonomi Denetimi
        if self._enable_break:
            if now - self._last_break_warn_time > self._break_interval:
                self._last_break_warn_time = now
                self._notify("Efendim, 1.5 saattir aralıksız çalışıyorsunuz. Kısa bir su molası verip gözlerinizi dinlendirmenizi öneririm.")

    def _loop(self) -> None:
        while self._running:
            self.check_once()
            # Uykuyu küçük adımlara bölerek stop() çağrısına anında yanıt ver
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
    Örnek: "proaktif uyarıları aç", "proaktif uyarıları kapat", "mola hatırlatıcısını aç", "bekçi durumu"
    """
    cleaned = user_text.lower().strip().strip(".!?,")
    sentinel = get_sentinel()

    if any(k in cleaned for k in ("proaktif uyarıları aç", "bekçiyi aç", "proaktif nöbetçiyi aç", "proaktif modu aç")):
        sentinel.enable_battery = True
        sentinel.enable_ram = True
        if not sentinel.is_running:
            sentinel.start()
        return "Proaktif sistem bekçisi aktif edildi. Düşük pil ve aşırı RAM durumunda sizi bilgilendireceğim."

    if any(k in cleaned for k in ("proaktif uyarıları kapat", "bekçiyi kapat", "proaktif nöbetçiyi kapat", "proaktif modu kapat")):
        sentinel.enable_battery = False
        sentinel.enable_ram = False
        sentinel.enable_break = False
        return "Proaktif sistem uyarıları kapatıldı."

    if any(k in cleaned for k in ("mola hatırlatıcıyı aç", "mola hatırlatıcısını aç", "su molasını aç", "mola uyarısını aç")):
        sentinel.enable_break = True
        if not sentinel.is_running:
            sentinel.start()
        return "Mola ve ergonomi hatırlatıcısı açıldı. Her 1.5 saatte bir dinlenme molası önereceğim."

    if any(k in cleaned for k in ("mola hatırlatıcıyı kapat", "mola hatırlatıcısını kapat", "su molasını kapat")):
        sentinel.enable_break = False
        return "Mola hatırlatıcısı kapatıldı."

    if any(k in cleaned for k in ("bekçi durumu", "proaktif durum", "proaktif bekçi durumu")):
        st_bat = "Açık" if sentinel.enable_battery else "Kapalı"
        st_ram = "Açık" if sentinel.enable_ram else "Kapalı"
        st_brk = "Açık" if sentinel.enable_break else "Kapalı"
        run_st = "Çalışıyor" if sentinel.is_running else "Durduruldu"
        return f"Proaktif Bekçi ({run_st}): Pil uyarısı: {st_bat}, RAM uyarısı: {st_ram}, Mola hatırlatıcı: {st_brk}."

    return None
