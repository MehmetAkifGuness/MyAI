import unittest
from unittest.mock import MagicMock

from boru.voice.listener import VoiceInputService
from boru.voice.speaker import VoiceOutputService


class VoiceServiceTests(unittest.TestCase):
    def test_voice_output_clean_text_for_speech(self):
        speaker = VoiceOutputService(enabled=True)
        raw_text = """
        Merhaba! İşte çözümün:
        ```python
        def test():
            return 42
        ```
        `test()` fonksiyonunu çalıştırabilirsin. Detaylar https://google.com adresinde.
        """
        cleaned = speaker.clean_text_for_speech(raw_text)
        self.assertNotIn("def test():", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertNotIn("https://", cleaned)
        self.assertIn("Merhaba!", cleaned)

    def test_voice_output_disabled_by_default_or_toggle(self):
        speaker = VoiceOutputService(enabled=False)
        self.assertFalse(speaker.enabled)
        # Speak çağrıldığında hiçbir işlem yapmamalı
        speaker.speak("Deneme mesajı", async_mode=False)

    def test_voice_input_mock_recognition(self):
        mock_recognizer = MagicMock()
        mock_microphone = MagicMock()
        mock_recognizer.recognize_google.return_value = "merhaba börü nasılsın"

        listener = VoiceInputService(
            recognizer=mock_recognizer,
            microphone=mock_microphone,
        )
        # _initialized = True yaparak sr importunu baypas edelim
        listener._initialized = True

        result = listener.listen_once()
        self.assertEqual(result, "merhaba börü nasılsın")
        mock_recognizer.recognize_google.assert_called_once()


if __name__ == "__main__":
    unittest.main()
