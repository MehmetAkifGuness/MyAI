"""
boru.voice — Sesli Konuşma ve Dinleme Paketi
============================================
"""

from boru.voice.listener import VoiceInputService
from boru.voice.speaker import VoiceOutputService

__all__ = [
    "VoiceInputService",
    "VoiceOutputService",
]
