from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _create_boru_tray_icon():
    """Börü için şık koyu-mavi ve altın kurt temalı sistem tepsisi ikonu üretir."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Dış mavi daire
    draw.ellipse((4, 4, 60, 60), fill="#161822", outline="#3182ce", width=3)
    # Altın kurt / üçgen sembolü
    draw.polygon([(18, 48), (32, 14), (46, 48), (32, 38)], fill="#ecc94b")
    return img


def is_startup_installed() -> bool:
    """Windows Başlangıç klasöründe Börü VBS dosyasının kurulu olup olmadığını kontrol eder."""
    try:
        import os
        from pathlib import Path
        appdata = os.environ.get("APPDATA")
        if appdata:
            p = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Boru_AI_Asistan.vbs"
            return p.exists()
    except Exception:
        pass
    return False


def toggle_startup_setting() -> None:
    """Windows Başlangıç ayarını tersine çevirir (Aktif <-> Pasif)."""
    try:
        from install_startup import install_startup, remove_startup
        if is_startup_installed():
            remove_startup()
        else:
            install_startup()
    except Exception as e:
        logger.debug(f"Başlangıç ayarı değiştirilemedi: {e}")


class BoruSystemTray:
    """
    Börü Windows Sistem Tepsisi (System Tray / Saatin Yanı) Yöneticisi.
    Pencere kapatıldığında arka planda sessizce Börü ve kısayolların çalışmasını sağlar.
    """

    def __init__(
        self,
        on_open: Optional[Callable[[], None]] = None,
        on_voice: Optional[Callable[[], None]] = None,
        on_spotlight: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        self._on_open = on_open
        self._on_voice = on_voice
        self._on_spotlight = on_spotlight
        self._on_exit = on_exit

        self._tray_icon = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> bool:
        """Sistem tepsisi ikonunu arka plan iş parçacığında başlatır."""
        try:
            import pystray

            menu = pystray.Menu(
                pystray.MenuItem("🐺 Börü'yü Göster", lambda: self._safe_call(self._on_open), default=True),
                pystray.MenuItem("🎙️ Sesli Sohbet (Ctrl+Shift+J)", lambda: self._safe_call(self._on_voice)),
                pystray.MenuItem("⚡ Börü Spotlight (Ctrl+Shift+B)", lambda: self._safe_call(self._on_spotlight)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "🚀 Windows ile Başlat",
                    lambda: toggle_startup_setting(),
                    checked=lambda item: is_startup_installed(),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("❌ Tamamen Kapat", lambda: self._handle_exit()),
            )

            icon_image = _create_boru_tray_icon()
            self._tray_icon = pystray.Icon(
                "BoruAssistant",
                icon_image,
                "🐺 Börü — Yapay Zeka Asistanı (Arka Planda Aktif)",
                menu=menu,
            )

            self._thread = threading.Thread(target=self._tray_icon.run, daemon=True, name="BoruTrayThread")
            self._thread.start()
            self._is_running = True
            logger.info("Börü Sistem Tepsisi (System Tray) başlatıldı.")
            return True
        except Exception as e:
            logger.debug(f"Sistem tepsisi başlatılamadı: {e}")
            return False

    def notify(self, title: str, message: str) -> None:
        """Windows bildirim baloncuğu gösterir."""
        if self._tray_icon and self._is_running:
            try:
                self._tray_icon.notify(message, title)
            except Exception:
                pass

    def stop(self) -> None:
        """Sistem tepsisi ikonunu kapatır."""
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        self._is_running = False

    def _safe_call(self, fn: Optional[Callable[[], None]]) -> None:
        if fn:
            try:
                fn()
            except Exception as e:
                logger.debug(f"Tray callback hatası: {e}")

    def _handle_exit(self) -> None:
        self.stop()
        if self._on_exit:
            try:
                self._on_exit()
            except Exception as e:
                logger.debug(f"Tray exit hatası: {e}")

