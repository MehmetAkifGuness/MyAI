from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from boru.tools.os_controller import (
    AutonomousComputerAgent,
    get_autonomous_computer_agent,
    resolve_os_controller_command,
)


class TestOSController:
    @pytest.fixture
    def agent(self) -> AutonomousComputerAgent:
        return AutonomousComputerAgent()

    def test_play_video_url(self, agent: AutonomousComputerAgent):
        with patch("webbrowser.open") as mock_open:
            ok, msg = agent.play_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            assert ok
            assert "Video doğrudan açıldı" in msg
            mock_open.assert_called_once_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_play_video_query(self, agent: AutonomousComputerAgent):
        with patch("webbrowser.open") as mock_open:
            ok, msg = agent.play_video("şu videoyu aç: Python dersi")
            assert ok
            assert "YouTube'da 'Python dersi' videosu açıldı." in msg
            mock_open.assert_called_once()
            call_url = mock_open.call_args[0][0]
            assert "search_query=Python+dersi" in call_url

    def test_play_music_spotify(self, agent: AutonomousComputerAgent):
        with patch("os.startfile") as mock_startfile, patch("webbrowser.open") as mock_open:
            ok, msg = agent.play_music("Duman", platform="spotify")
            assert ok
            assert "Spotify'da 'Duman'" in msg
            mock_startfile.assert_called_once()
            call_uri = mock_startfile.call_args[0][0]
            assert "spotify:search:Duman" in call_uri

    def test_play_music_youtube_music(self, agent: AutonomousComputerAgent):
        with patch("webbrowser.open") as mock_open:
            ok, msg = agent.play_music("Tarkan Kuzu Kuzu", platform="youtube_music")
            assert ok
            assert "YouTube Music'te" in msg
            mock_open.assert_called_once()
            call_url = mock_open.call_args[0][0]
            assert "music.youtube.com" in call_url

    def test_open_folder_standard(self, agent: AutonomousComputerAgent):
        with patch("subprocess.Popen") as mock_popen:
            ok, msg = agent.open_folder("indirilenler")
            assert ok
            assert "İndirilenler klasörü açıldı" in msg
            mock_popen.assert_called_once_with(["explorer.exe", "shell:Downloads"], shell=False)

        with patch("subprocess.Popen") as mock_popen:
            ok, msg = agent.open_folder("masaüstü klasörü")
            assert ok
            assert "Masaüstü klasörü açıldı" in msg
            mock_popen.assert_called_once_with(["explorer.exe", "shell:Desktop"], shell=False)

    def test_open_folder_project(self, agent: AutonomousComputerAgent):
        with patch("subprocess.Popen") as mock_popen:
            ok, msg = agent.open_folder("proje klasörü")
            assert ok
            assert "Proje klasörü açıldı" in msg
            mock_popen.assert_called_once()

    def test_open_folder_not_found(self, agent: AutonomousComputerAgent):
        ok, msg = agent.open_folder("olmayan_klasor_xyz_123")
        assert not ok
        assert "bulunamadı" in msg

    def test_take_screenshot(self, agent: AutonomousComputerAgent, tmp_path):
        mock_img = MagicMock()
        with patch("PIL.ImageGrab.grab", return_value=mock_img):
            ok, msg = agent.take_screenshot(target_dir=str(tmp_path))
            assert ok
            assert "Ekran görüntüsü başarıyla alındı ve kaydedildi" in msg
            mock_img.save.assert_called_once()

    def test_get_running_apps(self, agent: AutonomousComputerAgent):
        with patch("boru.tools.system_tools.get_top_processes", return_value=(True, "Chrome.exe")):
            ok, msg = agent.get_running_apps()
            assert ok
            assert "Chrome.exe" in msg

    def test_get_agent_help_summary(self, agent: AutonomousComputerAgent):
        summary = agent.get_agent_help_summary()
        assert "Börü Otonom Bilgisayar Ajanı" in summary
        assert "Google aç" in summary
        assert "YouTube aç" in summary
        assert "Şu videoyu aç" in summary
        assert "Spotify'da" in summary
        assert "İndirilenler klasörünü aç" in summary

    def test_resolve_os_controller_command_help(self):
        res1 = resolve_os_controller_command("bilgisayarımda ben sözle kontrol ediyormuşum gibi olur mu")
        assert res1 is not None
        assert "Börü Otonom Bilgisayar Ajanı" in res1

        res2 = resolve_os_controller_command("bilgisayarı sesle kontrol edebilir miyim")
        assert res2 is not None
        assert "Börü Otonom Bilgisayar Ajanı" in res2

        res3 = resolve_os_controller_command("otonom ajan mısın")
        assert res3 is not None
        assert "Börü Otonom Bilgisayar Ajanı" in res3

    def test_resolve_os_controller_command_video(self):
        with patch("webbrowser.open") as mock_open:
            res = resolve_os_controller_command("şu videoyu aç: Barış Manço Gülpembe")
            assert res is not None
            assert "Barış Manço Gülpembe" in res
            mock_open.assert_called_once()

        with patch("webbrowser.open") as mock_open:
            res = resolve_os_controller_command("işte şu videoyu aç Python tutorial")
            assert res is not None
            assert "Python tutorial" in res
            mock_open.assert_called_once()

        with patch("webbrowser.open") as mock_open:
            res = resolve_os_controller_command("youtube'da Barış Manço aç")
            assert res is not None
            assert "Barış Manço" in res
            mock_open.assert_called_once()

    def test_resolve_os_controller_command_music(self):
        with patch("os.startfile") as mock_start:
            res = resolve_os_controller_command("spotify'da Duman çal")
            assert res is not None
            assert "Spotify'da 'Duman'" in res
            mock_start.assert_called_once()

        with patch("os.startfile") as mock_start:
            res = resolve_os_controller_command("şu şarkıyı aç: Tarkan Kuzu Kuzu")
            assert res is not None
            assert "Tarkan Kuzu Kuzu" in res
            mock_start.assert_called_once()

    def test_resolve_os_controller_command_folder(self):
        with patch("subprocess.Popen") as mock_popen:
            res = resolve_os_controller_command("indirilenler klasörünü aç")
            assert res is not None
            assert "İndirilenler klasörü açıldı" in res
            mock_popen.assert_called_once()

    def test_resolve_os_controller_command_screenshot(self):
        mock_img = MagicMock()
        with patch("PIL.ImageGrab.grab", return_value=mock_img):
            res = resolve_os_controller_command("ekran görüntüsü al")
            assert res is not None
            assert "Ekran görüntüsü başarıyla alındı" in res

    def test_resolve_os_controller_command_unmatched(self):
        assert resolve_os_controller_command("Bugün hava nasıl?") is None
        assert resolve_os_controller_command("Python ile fibonacci yaz") is None
