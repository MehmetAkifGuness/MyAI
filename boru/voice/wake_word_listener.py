from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from boru.voice.continuous_dialogue import parse_wake_word

logger = logging.getLogger(__name__)


class BackgroundWakeWordListener:
    """
    Arka planda mikrofonu sürekli dinleyerek 'Börü' veya 'Hey Börü' uyandırma
    kelimesini yakalayan ve sistemi ayağa kaldıran hafif arka plan dinleyicisi.
    """

    def __init__(
        self,
        on_wake_word: Callable[[str], None],
        recognizer=None,
        microphone=None,
        language: str = "tr-TR",
    ):
        self._on_wake_word = on_wake_word
        self.language = language
        self._recognizer = recognizer
        self._microphone = microphone

        self._is_running = False
        self._is_paused = False
        self._stop_listening_fn: Optional[Callable[[bool], None]] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def _ensure_init(self) -> bool:
        try:
            import speech_recognition as sr

            if self._recognizer is None:
                self._recognizer = sr.Recognizer()
                self._recognizer.energy_threshold = 300
                self._recognizer.dynamic_energy_threshold = True

            if self._microphone is None:
                self._microphone = sr.Microphone()

            return True
        except Exception as e:
            logger.error(f"Mikrofon veya SpeechRecognition başlatılamadı: {e}")
            return False

    def start(self) -> bool:
        """Arka plan dinlemesini başlatır."""
        with self._lock:
            if self._is_running:
                return True

            if not self._ensure_init():
                return False

            try:
                import speech_recognition as sr

                with self._microphone as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.5)

                self._stop_listening_fn = self._recognizer.listen_in_background(
                    self._microphone,
                    self._audio_callback,
                    phrase_time_limit=4.0,
                )
                self._is_running = True
                self._is_paused = False
                logger.info("Arka plan 'Börü' sesli uyandırma dinleyicisi aktif.")
                return True
            except Exception as e:
                logger.error(f"listen_in_background başlatılamadı: {e}")
                return False

    def pause(self) -> None:
        """Diyalog sürerken veya Börü konuşurken arka plan dinleyicisini geçici duraklatır."""
        self._is_paused = True

    def resume(self) -> None:
        """Diyalog bittiğinde arka plan dinlemesini tekrar aktif eder."""
        self._is_paused = False

    def stop(self) -> None:
        """Arka plan dinleyicisini tamamen kapatır."""
        with self._lock:
            if not self._is_running:
                return

            if self._stop_listening_fn:
                try:
                    self._stop_listening_fn(wait_for_stop=False)
                except Exception:
                    pass
                self._stop_listening_fn = None

            self._is_running = False
            self._is_paused = False
            logger.info("Arka plan 'Börü' sesli uyandırma dinleyicisi durduruldu.")

    def _audio_callback(self, recognizer, audio) -> None:
        """SpeechRecognition tarafından arka planda ses algılandığında tetiklenir."""
        if not self._is_running or self._is_paused:
            return

        try:
            import speech_recognition as sr

            text = recognizer.recognize_google(audio, language=self.language)
            logger.debug(f"Arka plan ses algılandı: '{text}'")

            is_wake, remaining_cmd = parse_wake_word(text)
            if is_wake:
                logger.info(f"🐺 'Börü' uyandırma kelimesi algılandı! Komut: '{remaining_cmd}'")
                self.pause()
                try:
                    self._on_wake_word(remaining_cmd)
                except Exception as cb_err:
                    logger.error(f"Uyandırma callback hatası: {cb_err}")
        except Exception:
            # Gürültü, anlaşılamayan ses veya ağ zaman aşımı durumunda sessizce devam et
            pass
