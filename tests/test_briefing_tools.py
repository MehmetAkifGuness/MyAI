from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from boru.tools.briefing_tools import get_daily_briefing, resolve_briefing_command


class TestBriefingTools:
    def test_get_daily_briefing_format(self):
        with patch("boru.tools.quick_info.get_weather", return_value=(True, "Ankara için hava durumu: Açık +20°C.")):
            with patch("boru.tools.quick_info.get_currency_rate", return_value=(True, "1 Dolar şu anda yaklaşık 34.20 Türk Lirası seviyesinde.")):
                with patch("boru.tools.notes_tools.NotesService.list_notes", return_value=[{"id": 1, "text": "toplantı"}]):
                    with patch("boru.tools.system_tools.get_system_status", return_value=(True, "Sistem Durumu: RAM: %60 | Pil: %90")):
                        text = get_daily_briefing()
                        assert "efendim" in text
                        assert "Ankara için hava durumu" in text
                        assert "1 Dolar" in text
                        assert "toplantı" in text
                        assert "RAM: %60" in text
                        assert "göreve hazırım" in text

    def test_resolve_briefing_command(self):
        with patch("boru.tools.briefing_tools.get_daily_briefing", return_value="Brifing hazır efendim."):
            res1 = resolve_briefing_command("bana brifing ver")
            assert res1 == "Brifing hazır efendim."

            res2 = resolve_briefing_command("günün özeti")
            assert res2 == "Brifing hazır efendim."

            res3 = resolve_briefing_command("bugün ne var")
            assert res3 == "Brifing hazır efendim."

            assert resolve_briefing_command("nasılsın") is None
