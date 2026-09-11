from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from boru.tools.vision_tools import (
    capture_screen,
    get_available_vision_model,
    analyze_screen,
)


class TestVisionTools:
    def test_capture_screen_mock(self):
        mock_img = MagicMock()
        with patch("PIL.ImageGrab.grab", return_value=mock_img):
            ok, path = capture_screen()
            assert ok
            assert path.endswith(".png")
            mock_img.save.assert_called_once()

    def test_get_available_vision_model_detected(self):
        mock_response = MagicMock()
        mock_m1 = MagicMock()
        mock_m1.model = "qwen2.5-coder:7b"
        mock_m2 = MagicMock()
        mock_m2.model = "llava:latest"
        mock_response.models = [mock_m1, mock_m2]

        with patch("ollama.list", return_value=mock_response):
            found = get_available_vision_model()
            assert found == "llava:latest"

    def test_get_available_vision_model_none(self):
        mock_response = MagicMock()
        mock_m1 = MagicMock()
        mock_m1.model = "llama3.1:latest"
        mock_response.models = [mock_m1]

        with patch("ollama.list", return_value=mock_response):
            found = get_available_vision_model()
            assert found is None

    def test_analyze_screen_without_vision_model(self):
        with patch("boru.tools.vision_tools.capture_screen", return_value=(True, "dummy.png")), \
             patch("boru.tools.vision_tools.get_available_vision_model", return_value=None), \
             patch("os.path.exists", return_value=False):
            res = analyze_screen()
            assert "Ekran görüntüsü alındı" in res
            assert "vision modeli" in res

    def test_analyze_screen_with_vision_model(self):
        mock_chat_resp = MagicMock()
        mock_chat_resp.message.content = "Ekranda bir Python kod editörü açık."

        with patch("boru.tools.vision_tools.capture_screen", return_value=(True, "dummy.png")), \
             patch("boru.tools.vision_tools.get_available_vision_model", return_value="llava:latest"), \
             patch("builtins.open", MagicMock()), \
             patch("ollama.chat", return_value=mock_chat_resp), \
             patch("os.path.exists", return_value=False):
            res = analyze_screen()
            assert "Ekran İncelendi (llava:latest)" in res
            assert "Python kod editörü" in res

