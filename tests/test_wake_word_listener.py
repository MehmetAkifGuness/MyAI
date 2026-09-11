from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from boru.voice.wake_word_listener import BackgroundWakeWordListener


class TestBackgroundWakeWordListener:
    def test_init_and_state(self):
        callback = MagicMock()
        listener = BackgroundWakeWordListener(on_wake_word=callback)
        assert not listener.is_running
        assert not listener.is_paused

    def test_start_and_stop_with_mock(self):
        mock_rec = MagicMock()
        mock_mic = MagicMock()
        stop_fn = MagicMock()
        mock_rec.listen_in_background.return_value = stop_fn

        callback = MagicMock()
        listener = BackgroundWakeWordListener(
            on_wake_word=callback,
            recognizer=mock_rec,
            microphone=mock_mic,
        )

        started = listener.start()
        assert started is True
        assert listener.is_running
        assert not listener.is_paused
        mock_rec.listen_in_background.assert_called_once()

        listener.pause()
        assert listener.is_paused
        # pause() mikrofonu serbest bırakmak için stop_fn'i çağırmalı
        stop_fn.assert_called_once()

        listener.resume()
        assert not listener.is_paused
        # resume() arka plan dinlemesini yeniden bağlamalı
        assert mock_rec.listen_in_background.call_count == 2

        listener.stop()
        assert not listener.is_running
        assert stop_fn.call_count == 2

    def test_audio_callback_triggers_wake_word(self):
        callback = MagicMock()
        mock_rec = MagicMock()
        mock_mic = MagicMock()

        listener = BackgroundWakeWordListener(
            on_wake_word=callback,
            recognizer=mock_rec,
            microphone=mock_mic,
        )
        listener._is_running = True
        listener._is_paused = False

        # 1. Normal metin: Tetiklenmemeli
        mock_rec.recognize_google.return_value = "bugün hava çok güzel"
        listener._audio_callback(mock_rec, MagicMock())
        callback.assert_not_called()

        # 2. "Börü" uyandırma kelimesi: Tetiklenmeli ve duraklatılmalı
        mock_rec.recognize_google.return_value = "Hey Börü bu kodu açıkla"
        listener._audio_callback(mock_rec, MagicMock())
        callback.assert_called_once_with("bu kodu açıkla")
        assert listener.is_paused

    def test_audio_callback_ignored_when_paused(self):
        callback = MagicMock()
        mock_rec = MagicMock()

        listener = BackgroundWakeWordListener(
            on_wake_word=callback,
            recognizer=mock_rec,
            microphone=MagicMock(),
        )
        listener._is_running = True
        listener._is_paused = True

        mock_rec.recognize_google.return_value = "Börü"
        listener._audio_callback(mock_rec, MagicMock())
        callback.assert_not_called()

