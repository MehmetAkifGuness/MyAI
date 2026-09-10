"""
boru.voice — Sesli Konuşma ve Dinleme Paketi
============================================
"""

from boru.voice.listener import VoiceInputService, patch_speech_recognition_windows_console
from boru.voice.speaker import VoiceOutputService
from boru.voice.continuous_dialogue import (
    ContinuousVoiceController,
    WAKE_WORDS,
    is_stop_phrase,
    parse_wake_word,
)
from boru.voice.wake_word_listener import BackgroundWakeWordListener

# Windows konsol pencerelerinin açılmasını engelle
patch_speech_recognition_windows_console()

__all__ = [
    "VoiceInputService",
    "VoiceOutputService",
    "ContinuousVoiceController",
    "BackgroundWakeWordListener",
    "WAKE_WORDS",
    "is_stop_phrase",
    "parse_wake_word",
    "patch_speech_recognition_windows_console",
]
