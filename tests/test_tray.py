from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from boru.tray import BoruSystemTray, _create_boru_tray_icon


class TestBoruSystemTray:
    def test_create_boru_tray_icon(self):
        icon = _create_boru_tray_icon()
        assert icon.size == (64, 64)
        assert icon.mode == "RGBA"

    def test_start_and_stop_tray_with_mock(self):
        mock_icon = MagicMock()
        with patch("pystray.Icon", return_value=mock_icon):
            tray = BoruSystemTray(
                on_open=MagicMock(),
                on_voice=MagicMock(),
                on_spotlight=MagicMock(),
                on_exit=MagicMock(),
            )
            started = tray.start()
            assert started is True
            assert tray.is_running

            tray.notify("Başlık", "Mesaj")
            mock_icon.notify.assert_called_with("Mesaj", "Başlık")

            tray.stop()
            assert not tray.is_running
            mock_icon.stop.assert_called_once()

