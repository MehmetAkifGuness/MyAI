from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Win32 Modifier Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Virtual-Key Codes
VK_SPECIALS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


def parse_hotkey_string(hotkey_str: str) -> Tuple[int, int]:
    """
    Kullanıcı dostu metin formatını ('ctrl+shift+b', 'alt+space')
    Win32 fsModifiers ve Virtual-Key koduna dönüştürür.
    """
    parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"Geçersiz kısayol tanımı: '{hotkey_str}'")

    modifiers = MOD_NOREPEAT
    key_part = None

    for part in parts:
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part in ("shift",):
            modifiers |= MOD_SHIFT
        elif part in ("alt",):
            modifiers |= MOD_ALT
        elif part in ("win", "windows", "super"):
            modifiers |= MOD_WIN
        else:
            if key_part is not None:
                raise ValueError(f"Birden fazla anahtar tuş bulundu: {key_part}, {part}")
            key_part = part

    if not key_part:
        raise ValueError(f"Kısayol bir anahtar tuş içermelidir: '{hotkey_str}'")

    if key_part in VK_SPECIALS:
        vk = VK_SPECIALS[key_part]
    elif len(key_part) == 1:
        vk = ord(key_part.upper())
    else:
        raise ValueError(f"Tanınmayan tuş: '{key_part}'")

    return modifiers, vk


class GlobalHotkeyManager:
    """
    Windows üzerinde sistem geneli global klavye kısayollarını (hotkeys)
    yerel Win32 RegisterHotKey API'si ile dinleyen ve arka planda
    asenkron olarak callback fonksiyonlarını tetikleyen yönetici.
    """

    def __init__(self, win32_api=None):
        self._win32 = win32_api
        self._is_windows = (sys.platform == "win32") or (win32_api is not None)
        self._hotkeys: Dict[int, Tuple[str, int, int, Callable[[], None]]] = {}
        self._next_id = 1
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        self._ready_event = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    def register(self, hotkey_str: str, callback: Callable[[], None]) -> int:
        """
        Yeni bir global kısayol kaydeder.
        Örnek: manager.register("ctrl+shift+b", on_open_jarvis)
        """
        mods, vk = parse_hotkey_string(hotkey_str)
        hotkey_id = self._next_id
        self._next_id += 1
        self._hotkeys[hotkey_id] = (hotkey_str, mods, vk, callback)
        logger.info(f"Kısayol kaydedildi: {hotkey_str} (ID={hotkey_id})")
        return hotkey_id

    def start(self) -> bool:
        """
        Hotkey dinleyici arka plan thread'ini başlatır.
        """
        if self._running:
            return True

        if not self._is_windows:
            logger.warning("GlobalHotkeyManager sadece Windows işletim sisteminde çalışır.")
            return False

        self._running = True
        self._ready_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BoruGlobalHotkeyDaemon")
        self._thread.start()
        self._ready_event.wait(timeout=2.0)
        return True

    def stop(self) -> None:
        """
        Hotkey dinleyicisini ve arka plan thread'ini güvenle durdurur.
        """
        if not self._running:
            return

        self._running = False
        if self._thread_id and self._win32:
            try:
                # PostThreadMessageW ile WM_QUIT (0x0012) gönderip GetMessageW'den çıkar
                self._win32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            except Exception as e:
                logger.debug(f"PostThreadMessage hatası: {e}")

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None
        logger.info("GlobalHotkeyManager durduruldu.")

    def _get_user32(self):
        if self._win32 is not None:
            return self._win32
        try:
            import ctypes
            return ctypes.windll.user32
        except Exception as e:
            logger.error(f"ctypes.windll.user32 yüklenemedi: {e}")
            return None

    def _run_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = self._get_user32()
        if not user32:
            self._ready_event.set()
            return

        try:
            kernel32 = getattr(ctypes.windll, "kernel32", None)
            if kernel32 and hasattr(kernel32, "GetCurrentThreadId"):
                self._thread_id = kernel32.GetCurrentThreadId()
            else:
                self._thread_id = 1
        except Exception:
            self._thread_id = 1

        # Hotkey'leri bu thread'in mesaj kuyruğuna bağla (hWnd = None)
        registered_ids = []
        for hid, (hstr, mods, vk, _) in list(self._hotkeys.items()):
            try:
                res = user32.RegisterHotKey(None, hid, mods, vk)
                if res != 0:
                    registered_ids.append(hid)
                    logger.info(f"Win32 Hotkey başarıyla bağlandı: {hstr}")
                else:
                    logger.warning(f"Win32 Hotkey kaydedilemedi (çakışma olabilir): {hstr}")
            except Exception as e:
                logger.error(f"RegisterHotKey hatası ({hstr}): {e}")

        self._ready_event.set()

        msg = wintypes.MSG()
        WM_HOTKEY = 0x0312

        try:
            while self._running:
                # GetMessageW mesaj bekler (0 dönerse WM_QUIT gelmiştir)
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break

                if msg.message == WM_HOTKEY:
                    hid = msg.wParam
                    if hid in self._hotkeys:
                        _, _, _, cb = self._hotkeys[hid]
                        try:
                            cb()
                        except Exception as cb_err:
                            logger.error(f"Hotkey callback hatası (ID={hid}): {cb_err}")

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hid in registered_ids:
                try:
                    user32.UnregisterHotKey(None, hid)
                except Exception:
                    pass
            self._running = False
