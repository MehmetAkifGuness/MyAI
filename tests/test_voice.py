import unittest
from unittest.mock import MagicMock, patch

from boru.voice.listener import VoiceInputService
from boru.voice.speaker import (
    VoiceOutputService,
    VOICE_AHMET,
    VOICE_EMEL,
    get_voice_output_service,
    resolve_voice_settings_command,
)


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

    def test_split_into_sentences(self):
        speaker = VoiceOutputService(enabled=True)
        text = "Merhaba! <think>gizli düşünce</think> Bugün nasılsınız? Size nasıl yardımcı olabilirim."
        sentences = speaker.split_into_sentences(text)
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0], "Merhaba!")
        self.assertEqual(sentences[1], "Bugün nasılsınız?")
        self.assertEqual(sentences[2], "Size nasıl yardımcı olabilirim.")
        self.assertNotIn("gizli düşünce", " ".join(sentences))

    def test_voice_output_disabled_by_default_or_toggle(self):
        speaker = VoiceOutputService(enabled=False)
        self.assertFalse(speaker.enabled)
        speaker.speak("Deneme mesajı", async_mode=False)

    def test_voice_switch_and_toggle(self):
        speaker = VoiceOutputService(enabled=True, voice=VOICE_AHMET)
        self.assertEqual(speaker.voice, VOICE_AHMET)
        self.assertIn("Ahmet", speaker.get_current_voice())

        # Kadın sesine geç
        res = speaker.set_voice("kadın")
        self.assertEqual(speaker.voice, VOICE_EMEL)
        self.assertIn("Emel", res)

        # Toggle ile tekrar erkek sesine geç
        res2 = speaker.toggle_voice()
        self.assertEqual(speaker.voice, VOICE_AHMET)
        self.assertIn("Ahmet", res2)

    def test_voice_cache_path(self, tmp_path=None):
        speaker = VoiceOutputService(enabled=True)
        cache_path = speaker._get_cache_file("kısa bir test cümlesi")
        self.assertTrue(str(cache_path).endswith(".mp3"))

    def test_resolve_voice_settings_command(self):
        with patch.object(VoiceOutputService, "speak") as mock_speak:
            res1 = resolve_voice_settings_command("kadın sesine geç")
            self.assertIsNotNone(res1)
            self.assertIn("Emel", res1)

            res2 = resolve_voice_settings_command("erkek sesine geç")
            self.assertIsNotNone(res2)
            self.assertIn("Ahmet", res2)

            res3 = resolve_voice_settings_command("sesini değiştir")
            self.assertIsNotNone(res3)
            self.assertIn("değiştirdim", res3)

            res4 = resolve_voice_settings_command("hangi sesi kullanıyorsun")
            self.assertIsNotNone(res4)
            self.assertIn("aktif olan ses motorum", res4)

            self.assertIsNone(resolve_voice_settings_command("bu başka bir soru"))

    def test_voice_input_mock_recognition(self):
        mock_recognizer = MagicMock()
        mock_microphone = MagicMock()
        mock_recognizer.recognize_google.return_value = "merhaba börü nasılsın"

        listener = VoiceInputService(
            recognizer=mock_recognizer,
            microphone=mock_microphone,
        )
        listener._initialized = True

        result = listener.listen_once()
        self.assertEqual(result, "merhaba börü nasılsın")
        mock_recognizer.recognize_google.assert_called_once()

    def test_voice_input_offline_fallback(self):
        import speech_recognition as sr
        mock_recognizer = MagicMock()
        mock_microphone = MagicMock()
        mock_recognizer.recognize_google.side_effect = sr.RequestError("Network down")

        listener = VoiceInputService(
            recognizer=mock_recognizer,
            microphone=mock_microphone,
        )
        listener._initialized = True
        listener._recognize_offline_fallback = MagicMock(return_value="çevrimdışı algılanan metin")

        result = listener.listen_once()
        self.assertEqual(result, "çevrimdışı algılanan metin")
        listener._recognize_offline_fallback.assert_called_once()

    def test_patch_speech_recognition_windows_console(self):
        from unittest.mock import patch
        import os
        from boru.voice.listener import patch_speech_recognition_windows_console
        import speech_recognition as sr

        patch_speech_recognition_windows_console()
        self.assertTrue(getattr(sr.AudioData, "_boru_silent_patched", False))


if __name__ == "__main__":
    unittest.main()
