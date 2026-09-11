from __future__ import annotations

import time
from unittest.mock import MagicMock
import pytest

from boru.voice.continuous_dialogue import (
    ContinuousVoiceController,
    is_stop_phrase,
)


class TestStopPhraseDetector:
    def test_exact_stop_phrases(self):
        assert is_stop_phrase("kapat")
        assert is_stop_phrase("börü kapat")
        assert is_stop_phrase("görüşürüz")
        assert is_stop_phrase("hoşça kal")
        assert is_stop_phrase("tamamdır teşekkürler")
        assert is_stop_phrase("dur")
        assert is_stop_phrase("yeterli")
        assert is_stop_phrase("bu kadar")

    def test_tamam_is_not_a_stop_phrase(self):
        assert not is_stop_phrase("tamam")
        assert not is_stop_phrase("tamamdır")
        assert not is_stop_phrase("tamam şimdi kodu çalıştıralım")
        assert not is_stop_phrase("tamam bunu anladım")

    def test_phrases_with_punctuation(self):
        assert is_stop_phrase("Kapat!")
        assert is_stop_phrase("Teşekkürler.")
        assert is_stop_phrase("Görüşürüz.")

    def test_normal_queries_are_not_stop_phrases(self):
        assert not is_stop_phrase("test üret: boru/ui.py")
        assert not is_stop_phrase("bağımlılıkları göster")
        assert not is_stop_phrase("bugün hava nasıl")


class TestWakeWordDetector:
    def test_exact_wake_word(self):
        from boru.voice.continuous_dialogue import parse_wake_word

        is_wake, rem = parse_wake_word("Börü")
        assert is_wake
        assert rem == ""

        is_wake, rem = parse_wake_word("Hey Börü!")
        assert is_wake
        assert rem == ""

    def test_wake_word_with_command(self):
        from boru.voice.continuous_dialogue import parse_wake_word

        is_wake, rem = parse_wake_word("Börü bu fonksiyonu test et")
        assert is_wake
        assert rem == "bu fonksiyonu test et"

        is_wake, rem = parse_wake_word("Hey Börü, git status çalıştır")
        assert is_wake
        assert rem == "git status çalıştır"

    def test_wake_word_with_greetings_and_suffix(self):
        from boru.voice.continuous_dialogue import parse_wake_word

        is_wake, rem = parse_wake_word("Merhaba Börü")
        assert is_wake
        assert rem == ""

        is_wake, rem = parse_wake_word("Selam Börü nasılsın")
        assert is_wake
        assert rem == "nasılsın"

        is_wake, rem = parse_wake_word("Hava durumu nasıl Börü")
        assert is_wake
        assert rem == "Hava durumu nasıl"

    def test_no_wake_word(self):
        from boru.voice.continuous_dialogue import parse_wake_word

        is_wake, rem = parse_wake_word("pytest tests çalıştır")
        assert not is_wake
        assert rem == "pytest tests çalıştır"


class TestContinuousVoiceController:
    def test_dialogue_single_interaction_and_stop(self):
        mock_input = MagicMock()
        mock_output = MagicMock()

        # İlk döngüde normal soru, ikinci döngüde "tamamdır" kapatma komutu
        mock_input.listen_once.side_effect = [
            "Börü bugün nasılsın",
            "tamamdır teşekkürler",
        ]

        replies_sent = []

        def on_speech(text):
            reply = f"Cevap: {text}"
            replies_sent.append(reply)
            return reply

        status_history = []

        def on_status(text, color):
            status_history.append(text)

        ended_event = False

        def on_ended():
            nonlocal ended_event
            ended_event = True

        controller = ContinuousVoiceController(
            voice_input=mock_input,
            voice_output=mock_output,
            on_user_speech=on_speech,
            on_status_change=on_status,
            on_dialogue_ended=on_ended,
        )

        controller.start()
        # Thread'in iki mesajı işlemesini bekle
        time.sleep(0.5)
        controller.stop()

        assert len(replies_sent) >= 1
        assert "Cevap: bugün nasılsın" in replies_sent[0]
        # Börü yanıtı seslendirdi mi?
        mock_output.speak.assert_called()
        assert not controller.is_active

    def test_timeout_handling(self):
        mock_input = MagicMock()
        mock_output = MagicMock()

        # İki kez üst üste TimeoutError verip sonlanmasını sağla
        mock_input.listen_once.side_effect = TimeoutError()

        controller = ContinuousVoiceController(
            voice_input=mock_input,
            voice_output=mock_output,
            on_user_speech=lambda _: "cevabım",
        )

        controller.start()
        time.sleep(0.4)
        assert not controller.is_active

