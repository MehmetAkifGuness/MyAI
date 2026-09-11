from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from boru.sentinel import SentinelService, resolve_sentinel_command, get_sentinel


class TestSentinel:
    def test_battery_low_alert_and_no_spam(self):
        mock_speak = MagicMock()
        service = SentinelService(speak_fn=mock_speak, check_interval_seconds=1.0)

        with patch("ctypes.windll.kernel32.GetSystemPowerStatus") as mock_power:
            def side_effect(byref_p):
                p = byref_p._obj
                p.BatteryLifePercent = 12
                p.ACLineStatus = 0
                return 1
            mock_power.side_effect = side_effect

            # 1. İlk kontrolde uyarmalı
            service.check_once()
            assert mock_speak.call_count == 1
            assert "yüzde 12" in mock_speak.call_args[0][0]

            # 2. İkinci kontrolde aynı boşalma döngüsünde spam yapmamalı
            service.check_once()
            assert mock_speak.call_count == 1

            # 3. Şarja takıldığında durum sıfırlanmalı
            def charged_effect(byref_p):
                p = byref_p._obj
                p.BatteryLifePercent = 50
                p.ACLineStatus = 1
                return 1
            mock_power.side_effect = charged_effect
            service.check_once()

            # 4. Tekrar düşerse yine uyarmalı
            mock_power.side_effect = side_effect
            service.check_once()
            assert mock_speak.call_count == 2

    def test_ram_high_alert(self):
        mock_speak = MagicMock()
        service = SentinelService(speak_fn=mock_speak, check_interval_seconds=1.0)

        with patch("ctypes.windll.kernel32.GlobalMemoryStatusEx") as mock_mem:
            def mem_effect(byref_m):
                m = byref_m._obj
                m.dwMemoryLoad = 95
                return 1
            mock_mem.side_effect = mem_effect

            with patch("boru.tools.system_tools.get_top_processes", return_value=(True, "Chrome.exe (1200 MB)")):
                service.check_once()
                assert mock_speak.call_count == 1
                assert "yüzde 95" in mock_speak.call_args[0][0]

    def test_resolve_sentinel_command(self):
        res1 = resolve_sentinel_command("proaktif uyarıları aç")
        assert "aktif edildi" in res1
        assert get_sentinel().enable_battery is True

        res2 = resolve_sentinel_command("mola hatırlatıcısını aç")
        assert "açıldı" in res2
        assert get_sentinel().enable_break is True

        res3 = resolve_sentinel_command("bekçi durumu")
        assert "Pil uyarısı: Açık" in res3
        assert "Mola hatırlatıcı: Açık" in res3

        res4 = resolve_sentinel_command("proaktif uyarıları kapat")
        assert "kapatıldı" in res4
        assert get_sentinel().enable_battery is False

