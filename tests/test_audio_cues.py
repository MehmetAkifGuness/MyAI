from __future__ import annotations

import io
import wave
from unittest.mock import MagicMock, patch
import pytest

from boru.voice.audio_cues import AudioCueService, _generate_wav_bytes


class TestAudioCueService:
    def test_generate_wav_bytes_structure(self):
        wav_bytes = _generate_wav_bytes([(440.0, 880.0)], duration=0.1, sample_rate=22050, volume=0.2)
        assert len(wav_bytes) > 100
        # Valid WAV header check
        with wave.open(io.BytesIO(wav_bytes), "rb") as r:
            assert r.getnchannels() == 1
            assert r.getsampwidth() == 2
            assert r.getframerate() == 22050
            frames = r.readframes(r.getnframes())
            assert len(frames) > 0

    def test_audio_cue_service_disabled_does_not_play(self):
        cue = AudioCueService(enabled=False)
        with patch.object(cue, "_get_sound") as mock_get:
            cue.play_wake()
            cue.play_listen_start()
            cue.play_listen_stop()
            cue.play_success()
            cue.play_error()
            mock_get.assert_not_called()

    def test_audio_cue_service_play_methods_generate_sounds(self):
        mock_sound = MagicMock()
        with patch("pygame.mixer.Sound", return_value=mock_sound), \
             patch("pygame.mixer.init"), \
             patch("pygame.mixer.get_init", return_value=True):
            cue = AudioCueService(enabled=True)
            cue.play_wake()
            cue.play_listen_start()
            cue.play_listen_stop()
            cue.play_success()
            cue.play_error()
            # Wait for thread execution
            import time
            time.sleep(0.3)
            assert mock_sound.play.call_count >= 1

