from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class VoiceInputService:
    """
    Mikrofondan Türkçe konuşmaları algılayıp metne dönüştüren servis.
    SpeechRecognition ve PyAudio altyapısını kullanır.
    """

    def __init__(self, recognizer=None, microphone=None, language: str = "tr-TR"):
        self.language = language
        self._recognizer = recognizer
        self._microphone = microphone
        self._initialized = False

    def _ensure_init(self):
        if not self._initialized:
            try:
                import speech_recognition as sr
                if self._recognizer is None:
                    self._recognizer = sr.Recognizer()
                if self._microphone is None:
                    self._microphone = sr.Microphone()
                self._initialized = True
            except Exception as e:
                logger.error(f"Mikrofon veya SpeechRecognition başlatılamadı: {e}")
                raise RuntimeError(f"Ses tanıma motoru başlatılamadı: {e}")

    def listen_once(self, timeout: float = 5.0, phrase_time_limit: float = 10.0) -> str:
        """
        Mikrofonu dinler ve konuşulan metni Türkçe olarak döndürür.
        """
        self._ensure_init()
        import speech_recognition as sr

        try:
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = self._recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )

            text = self._recognizer.recognize_google(audio, language=self.language)
            return text.strip()
        except sr.WaitTimeoutError:
            raise TimeoutError("Herhangi bir ses algılanamadı (zaman aşımı).")
        except sr.UnknownValueError:
            raise ValueError("Söylenen anlaşılamadı, lütfen tekrar edin.")
        except sr.RequestError as e:
            raise RuntimeError(f"Ses tanıma servisine ulaşılamadı: {e}")
