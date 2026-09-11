from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest

from boru.tools.clipboard_tools import get_clipboard_text, resolve_clipboard_command


class TestClipboardTools:
    def test_get_clipboard_text_mock(self):
        with patch("tkinter.Tk") as mock_tk:
            mock_inst = MagicMock()
            mock_inst.clipboard_get.return_value = "Merhaba Dünya"
            mock_tk.return_value = mock_inst
            assert get_clipboard_text() == "Merhaba Dünya"

    def test_resolve_clipboard_command(self):
        with patch("boru.tools.clipboard_tools.get_clipboard_text", return_value="Python list comprehension"):
            res = resolve_clipboard_command("panoda ne var")
            assert "Panodaki metin:" in res
            assert "Python list comprehension" in res

        with patch("boru.tools.clipboard_tools.get_clipboard_text", return_value=""):
            res = resolve_clipboard_command("panoyu oku")
            assert "herhangi bir metin bulunmuyor" in res

        with patch("boru.tools.clipboard_tools.get_clipboard_text", return_value="Hello world"):
            with patch("boru.tools.clipboard_tools._query_ollama", return_value="Selam dünya") as mock_llm:
                res = resolve_clipboard_command("panoyu çevir")
                assert res == "Selam dünya"
                mock_llm.assert_called_once()

        assert resolve_clipboard_command("bunu yapma") is None
