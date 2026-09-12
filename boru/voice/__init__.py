"""
boru.voice — Sesli Konuşma ve Dinleme Paketi
============================================
"""

from boru.voice.listener import VoiceInputService, patch_speech_recognition_windows_console
from boru.voice.speaker import (
    VoiceOutputService,
    get_voice_output_service,
    resolve_voice_settings_command,
)
from boru.voice.continuous_dialogue import (
    ContinuousVoiceController,
    WAKE_WORDS,
    is_stop_phrase,
    parse_wake_word,
)
from boru.voice.audio_cues import AudioCueService
from boru.voice.wake_word_listener import BackgroundWakeWordListener

# Windows konsol pencerelerinin açılmasını engelle
patch_speech_recognition_windows_console()

__all__ = [
    "VoiceInputService",
    "VoiceOutputService",
    "get_voice_output_service",
    "resolve_voice_settings_command",
    "ContinuousVoiceController",
    "BackgroundWakeWordListener",
    "AudioCueService",
    "WAKE_WORDS",
    "is_stop_phrase",
    "parse_wake_word",
    "patch_speech_recognition_windows_console",
]
