from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from boru.tools.web_qa_tools import search_wikipedia_summary, resolve_web_qa_command


class TestWebQATools:
    def test_search_wikipedia_summary_mock(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"extract": "Baris Manco Turk sarkici ve bestecidir. Cok unludur."}'
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            ok, summary = search_wikipedia_summary("Barış Manço")
            assert ok
            assert "Baris Manco" in summary

    def test_resolve_web_qa_command_who_what(self):
        with patch("boru.tools.web_qa_tools.search_wikipedia_summary", return_value=(True, "Ataturk Turkiye Cumhuriyeti kurucusudur.")):
            res1 = resolve_web_qa_command("Atatürk kimdir?")
            assert res1 == "Ataturk Turkiye Cumhuriyeti kurucusudur."

            res2 = resolve_web_qa_command("kuantum bilgisayar nedir")
            assert res2 == "Ataturk Turkiye Cumhuriyeti kurucusudur."

            res3 = resolve_web_qa_command("yapay zeka hakkında bilgi ver")
            assert res3 == "Ataturk Turkiye Cumhuriyeti kurucusudur."

    def test_resolve_web_qa_command_rejects_system_keywords(self):
        assert resolve_web_qa_command("ram nedir") is None
        assert resolve_web_qa_command("pil nedir") is None
        assert resolve_web_qa_command("sesi aç") is None
