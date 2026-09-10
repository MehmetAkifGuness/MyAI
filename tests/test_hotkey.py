from __future__ import annotations

import ctypes
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from boru.hotkey.global_hotkey import (
    GlobalHotkeyManager,
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    parse_hotkey_string,
)


class TestHotkeyParser:
    def test_parse_ctrl_shift_b(self):
        mods, vk = parse_hotkey_string("ctrl+shift+b")
        assert mods == (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT)
        assert vk == ord("B")

    def test_parse_alt_space(self):
        mods, vk = parse_hotkey_string("alt+space")
        assert mods == (MOD_ALT | MOD_NOREPEAT)
        assert vk == 0x20

    def test_parse_ctrl_shift_j(self):
        mods, vk = parse_hotkey_string("ctrl+shift+j")
        assert mods == (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT)
        assert vk == ord("J")

    def test_parse_super_or_win(self):
        mods, vk = parse_hotkey_string("win+f1")
        assert mods == (MOD_WIN | MOD_NOREPEAT)
        assert vk == 0x70

    def test_parse_invalid_empty(self):
        with pytest.raises(ValueError):
            parse_hotkey_string("")

    def test_parse_no_key(self):
        with pytest.raises(ValueError):
            parse_hotkey_string("ctrl+shift")

    def test_parse_unknown_key(self):
        with pytest.raises(ValueError):
            parse_hotkey_string("ctrl+superlongunknownkey")


class TestGlobalHotkeyManager:
    def test_register_records_hotkey(self):
        manager = GlobalHotkeyManager()
        callback = MagicMock()
        hid = manager.register("ctrl+shift+b", callback)
        assert hid == 1
        assert 1 in manager._hotkeys
        hstr, mods, vk, cb = manager._hotkeys[1]
        assert hstr == "ctrl+shift+b"
        assert mods == (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT)
        assert vk == ord("B")
        assert cb == callback

    def test_start_and_trigger_mock_win32(self):
        mock_win32 = MagicMock()
        mock_win32.RegisterHotKey.return_value = 1
        mock_win32.UnregisterHotKey.return_value = 1

        # Simüle edilecek mesajlar: İlk çağrıda WM_HOTKEY (ID=1), ikinci çağrıda WM_QUIT (0)
        call_count = 0

        def fake_get_message(msg_ptr, hwnd, min_val, max_val):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # msg_ptr ctypes byref nesnesidir
                msg = msg_ptr._obj
                msg.message = 0x0312  # WM_HOTKEY
                msg.wParam = 1
                return 1
            return 0  # WM_QUIT

        mock_win32.GetMessageW.side_effect = fake_get_message

        manager = GlobalHotkeyManager(win32_api=mock_win32)
        callback_called = threading.Event()

        def on_pressed():
            callback_called.set()

        hid = manager.register("ctrl+shift+b", on_pressed)
        started = manager.start()
        assert started is True

        # Callback tetiklendi mi?
        assert callback_called.wait(timeout=2.0)
        manager.stop()

        assert not manager.is_running
        mock_win32.RegisterHotKey.assert_called_once()
        mock_win32.UnregisterHotKey.assert_called_once()

    def test_stop_gracefully_when_not_started(self):
        manager = GlobalHotkeyManager()
        # Başlatılmamış yöneticide stop çağırmak hata vermemelidir
        manager.stop()
        assert not manager.is_running
