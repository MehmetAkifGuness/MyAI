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

        # Saat & Tarih testleri
        time_res = resolve_quick_info("saat kaç")
        assert time_res is not None and "saat" in time_res

        day_res = resolve_quick_info("bugün günlerden ne")
        assert day_res is not None and "günlerden" in day_res

        day_res2 = resolve_quick_info("Peki günlerden ne")
        assert day_res2 is not None and "günlerden" in day_res2

        year_res = resolve_quick_info("hangi yıldayız")
        assert year_res is not None and "yılındayız" in year_res

        date_res1 = resolve_quick_info("ay gün yıl olarak")
        assert date_res1 is not None and "Gün:" in date_res1 and "Yıl:" in date_res1

        date_res2 = resolve_quick_info("bugünü gün ay yıl olarak göster")
        assert date_res2 is not None and "Gün:" in date_res2 and "Yıl:" in date_res2

        # Gelişmiş Şehir Çıkarımı Testleri (Stopword ve Bilinen Şehirler)
        with patch("boru.tools.quick_info.get_weather", return_value=(True, "Kahramanmaraş için hava durumu: Açık +29°C.")) as mock_w:
            res = resolve_quick_info("Kahramanmaraş için şu anki hava durumunu söyle")
            assert "Kahramanmaraş" in res
            mock_w.assert_called_with("kahramanmaraş")

            # "o zaman hava durumu" -> "zaman" kelimesi stopword olduğundan şehir olarak alınmamalıdır
            res_zaman = resolve_quick_info("o zaman hava durumu")
            mock_w.assert_called_with("Istanbul")

        # Gelişmiş Döviz Kuru Testleri (Azerbaycan Manatı, Japon Yeni vb.)
        with patch("boru.tools.quick_info.get_currency_rate", return_value=(True, "1 Azerbaycan Manatı: 28.51 TL")) as mock_fx:
            res_manat = resolve_quick_info("Peki Azerbaycan manatı ne kadar")
            assert "Azerbaycan Manatı" in res_manat
            mock_fx.assert_called_with("AZN", "TRY")

            resolve_quick_info("1 manat kaç tl")
            mock_fx.assert_called_with("AZN", "TRY")

            resolve_quick_info("japon yeni kaç lira")
            mock_fx.assert_called_with("JPY", "TRY")

        # Matematik testleri
        assert resolve_quick_info("125 çarpı 48 kaç eder") == "125 × 48 = 6000 eder."
        assert resolve_quick_info("840 bölü 12 kaçtır") == "840 ÷ 12 = 70 eder."
        assert resolve_quick_info("1500 liranın yüzde 20'si kaç") == "1500 sayısının %20'si = 300 eder."
        assert resolve_quick_info("100 / 0") == "Sıfıra bölme işlemi tanımsızdır."

        assert resolve_quick_info("merhaba nasılsın") is None

