"""
tests/test_self_correction_strategies.py
=========================================
Börü Self-Correction ve Çok Kademeli Strateji Değiştirme Birim Testleri.
"""

from unittest.mock import MagicMock, patch
import pytest

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.prompts import SystemPromptFactory
from boru.tools.self_corrector import ActionHistoryTracker, SelfCorrectionDispatcher
from boru.tools.system_tools import resolve_system_command


class TestSelfCorrectionStrategies:
    """Hatadan ders çıkarma ve alternatif stratejilere geçiş testleri."""

    def setup_method(self):
        ActionHistoryTracker.get_instance().clear()

    def test_action_history_tracker_records_and_retrieves(self):
        tracker = ActionHistoryTracker.get_instance()
        tracker.record_action("close_app", "chrome", strategy_tier=1, success=False)
        last = tracker.get_last_action()
        assert last is not None
        assert last.action_type == "close_app"
        assert last.target == "chrome"
        assert last.strategy_tier == 1
        assert last.success is False

    @patch("boru.tools.closed_loop.ClosedLoopActionExecutor.close_app_verified")
    def test_handle_correction_escalates_close_app_to_tier2(self, mock_close_verified):
        mock_close_verified.return_value = (True, "Doğrulandı: Chrome kapatıldı.")
        tracker = ActionHistoryTracker.get_instance()
        tracker.record_action("close_app", "chrome", strategy_tier=1, success=False)

        # Kullanıcı 'Hala açık' dediğinde Strateji 2 (Force Tree Kill) devreye girmeli
        res = SelfCorrectionDispatcher.handle_correction("Hala açık duruyor")
        assert res is not None
        assert "Zorla Ağaç Sonlandırma" in res or "Force Kill" in res
        assert "Chrome" in res

        # Doğrula: close_app_verified force_tree=True ile çağrıldı mı
        mock_close_verified.assert_called_once_with("chrome", force_tree=True)
        assert tracker.get_last_action().strategy_tier == 2

    @patch("webbrowser.open")
    def test_handle_correction_escalates_music_to_youtube_fallback(self, mock_web_open):
        tracker = ActionHistoryTracker.get_instance()
        tracker.record_action("play_music", "Ceza Sus Pus", strategy_tier=1, success=True)

        # Kullanıcı 'şarkı çalmadı' dediğinde YouTube web fallback stratejisi uygulanmalı
        res = SelfCorrectionDispatcher.handle_correction("şarkı çalmadı")
        assert res is not None
        assert "YouTube Web üzerinde" in res
        mock_web_open.assert_called_once()
        assert "youtube.com" in mock_web_open.call_args[0][0]

    def test_handle_correction_returns_none_when_no_recent_action(self):
        tracker = ActionHistoryTracker.get_instance()
        tracker.clear()
        res = SelfCorrectionDispatcher.handle_correction("Hala açık")
        assert res is None

    @patch("boru.tools.closed_loop.ClosedLoopActionExecutor.close_app_verified")
    def test_system_command_resolver_intercepts_correction_before_feedback(self, mock_close_verified):
        mock_close_verified.return_value = (True, "Doğrulandı: Notepad kapatıldı.")
        tracker = ActionHistoryTracker.get_instance()
        tracker.record_action("close_app", "notepad", strategy_tier=1, success=False)

        # resolve_system_command doğrudan SelfCorrection yanıtını döndürmelidir
        res = resolve_system_command("Kapanmadı ki")
        assert res is not None
        assert "Zorla Ağaç Sonlandırma" in res or "Force Kill" in res
        mock_close_verified.assert_called_once()

    @patch("boru.tools.closed_loop.ClosedLoopActionExecutor.close_app_verified")
    def test_assistant_end_to_end_self_correction(self, mock_close_verified):
        mock_close_verified.return_value = (True, "Doğrulandı: Chrome kapatıldı.")
        tracker = ActionHistoryTracker.get_instance()
        tracker.record_action("close_app", "chrome", strategy_tier=1, success=False)

        mock_model = MagicMock()
        history = ConversationHistory()
        prompt_factory = SystemPromptFactory("Börü", conversational=True)

        assistant = AssistantService(
            chat_model=mock_model,
            conversation_history=history,
            prompt_factory=prompt_factory,
        )

        # Kullanıcı 'Hala açık' dediğinde LLM'e gitmeden doğrudan 2. Seviye Düzeltme çalışmalı
        reply = assistant.reply("Hala açık duruyor")
        mock_model.generate_response.assert_not_called()
        assert "Zorla Ağaç Sonlandırma" in reply or "Force Kill" in reply

