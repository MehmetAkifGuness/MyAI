from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from boru.tools.system_tools import (
    open_application,
    control_volume,
    get_system_status,
    search_web,
    resolve_system_command,
)


class TestSystemTools:
    def test_open_application_mock(self):
        with patch("subprocess.Popen") as mock_popen, patch("os.startfile"):
            ok, msg = open_application("notepad")
            assert ok
            assert "Notepad açıldı" in msg

    def test_control_volume_up_down_mute(self):
        with patch("ctypes.windll.user32.keybd_event") as mock_key:
            ok, msg = control_volume("up")
            assert ok
            assert "artırıldı" in msg
            assert mock_key.call_count > 0

            ok, msg = control_volume("down")
            assert ok
            assert "kısıldı" in msg

            ok, msg = control_volume("mute")
            assert ok
            assert "sessize" in msg

    def test_get_system_status(self):
        ok, msg = get_system_status()
        assert ok
        assert "Sistem" in msg

    def test_search_web_google_and_youtube(self):
        with patch("webbrowser.open") as mock_browser:
            ok, msg = search_web("python test", platform="google")
            assert ok
            assert "Google" in msg
            mock_browser.assert_called_once()

        with patch("webbrowser.open") as mock_browser:
            ok, msg = search_web("tarkan", platform="youtube")
            assert ok
            assert "YouTube" in msg
            mock_browser.assert_called_once()

    def test_resolve_system_command_patterns(self):
        with patch("boru.tools.system_tools.open_application", return_value=(True, "Spotify açıldı.")):
            res = resolve_system_command("spotify aç")
            assert res == "Spotify açıldı."

            res = resolve_system_command("lütfen spotify'ı aç")
            assert res == "Spotify açıldı."

        with patch("boru.tools.system_tools.control_volume", return_value=(True, "Ses artırıldı.")):
            res = resolve_system_command("sesi yükselt")
            assert res == "Ses artırıldı."

        with patch("boru.tools.system_tools.get_system_status", return_value=(True, "Pil: %100")):
            res = resolve_system_command("pil durumu")
            assert res == "Pil: %100"

        # Eşleşmeyen komut None dönmeli
        assert resolve_system_command("Python fonksiyonu nasıl yazılır?") is None
