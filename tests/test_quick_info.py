from __future__ import annotations

from unittest.mock import patch, MagicMock
import io
import json
import pytest

from boru.tools.quick_info import get_weather, get_currency_rate, resolve_quick_info


class TestQuickInfo:
    def test_get_weather_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"Gunesli +22C"
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, msg = get_weather("Izmir")
            assert ok
            assert "Izmir için hava durumu: Gunesli +22C." in msg

    def test_get_currency_rate_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"rates": {"TRY": 34.5}}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, msg = get_currency_rate("USD", "TRY")
            assert ok
            assert "Dolar" in msg
            assert "34.50" in msg

    def test_resolve_quick_info_patterns(self):
        with patch("boru.tools.quick_info.get_weather", return_value=(True, "Istanbul hava durumu: Açık")):
            assert resolve_quick_info("hava durumu") == "Istanbul hava durumu: Açık"
            assert resolve_quick_info("bugün hava nasıl") == "Istanbul hava durumu: Açık"

        with patch("boru.tools.quick_info.get_currency_rate", return_value=(True, "1 Dolar: 34.5 TL")):
            assert resolve_quick_info("dolar kaç tl") == "1 Dolar: 34.5 TL"
            assert resolve_quick_info("dolar ne kadar") == "1 Dolar: 34.5 TL"

        assert resolve_quick_info("merhaba nasılsın") is None

