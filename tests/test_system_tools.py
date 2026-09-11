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

        with patch("boru.tools.system_tools.open_application", return_value=(True, "YouTube açıldı.")) as mock_open:
            res = resolve_system_command("youtube aç")
            assert res == "YouTube açıldı."
            mock_open.assert_called_with("youtube")

            res = resolve_system_command("youtube'u aç")
            assert res == "YouTube açıldı."

            res = resolve_system_command("aç youtube")
            assert res == "YouTube açıldı."

        with patch("boru.tools.system_tools.open_application", return_value=(True, "Not defteri açıldı.")) as mock_open:
            res = resolve_system_command("not defterini aç")
            assert res == "Not defteri açıldı."
            mock_open.assert_called_with("not defteri")

        with patch("boru.tools.system_tools.control_volume", return_value=(True, "Ses artırıldı.")):
            res = resolve_system_command("sesi yükselt")
            assert res == "Ses artırıldı."

        with patch("boru.tools.system_tools.get_system_status", return_value=(True, "Pil: %100")):
            res = resolve_system_command("pil durumu")
            assert res == "Pil: %100"

        with patch("boru.tools.system_tools.search_web", return_value=(True, "Google'da arama açıldı.")) as mock_search:
            res = resolve_system_command("google'da hava durumu ara")
            assert res == "Google'da arama açıldı."
            mock_search.assert_called_with("hava durumu", platform="google")

            res = resolve_system_command("internette yapay zeka ara")
            assert res == "Google'da arama açıldı."

        with patch("boru.tools.system_tools.control_media", return_value=(True, "Medya oynatıldı / duraklatıldı.")) as mock_media:
            res = resolve_system_command("müziği durdur")
            assert res == "Medya oynatıldı / duraklatıldı."
            mock_media.assert_called_with("play_pause")

            res = resolve_system_command("sonraki şarkı")
            assert res == "Medya oynatıldı / duraklatıldı."
            mock_media.assert_called_with("next")

            res = resolve_system_command("önceki parça")
            assert res == "Medya oynatıldı / duraklatıldı."
            mock_media.assert_called_with("prev")

        with patch("boru.tools.system_tools.show_desktop", return_value=(True, "Masaüstü gösterildi.")) as mock_desk:
            res = resolve_system_command("masaüstünü göster")
            assert res == "Masaüstü gösterildi."
            mock_desk.assert_called_once()

        with patch("boru.tools.system_tools.lock_workstation", return_value=(True, "Bilgisayar kilitlendi.")) as mock_lock:
            res = resolve_system_command("bilgisayarı kilitle")
            assert res == "Bilgisayar kilitlendi."
            mock_lock.assert_called_once()

        with patch("boru.tools.system_tools.cancel_shutdown", return_value=(True, "İptal edildi.")) as mock_cancel:
            res = resolve_system_command("kapatmayı iptal et")
            assert res == "İptal edildi."
            mock_cancel.assert_called_once()

        with patch("boru.tools.system_tools.close_application", return_value=(True, "Chrome kapatıldı.")) as mock_close:
            res = resolve_system_command("chrome'u kapat")
            assert res == "Chrome kapatıldı."
            mock_close.assert_called_with("chrome")

            res = resolve_system_command("not defterini kapat")
            assert res == "Chrome kapatıldı."

        with patch("boru.tools.system_tools.get_top_processes", return_value=(True, "En çok bellek kullananlar: Code.exe")) as mock_top:
            res = resolve_system_command("hangi program çok ram yiyor")
            assert "Code.exe" in res

        # Eşleşmeyen komut None dönmeli
        assert resolve_system_command("Python fonksiyonu nasıl yazılır?") is None

    def test_close_application_mock(self):
        from boru.tools.system_tools import close_application
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok, msg = close_application("chrome")
            assert ok
            assert "Chrome kapatıldı" in msg

            mock_run.return_value = MagicMock(returncode=1)
            ok, msg = close_application("bilinmeyen_app")
            assert not ok
            assert "açık değil veya kapatılamadı" in msg

