from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def patch_speech_recognition_windows_console() -> None:
    """
    Windows'ta speech_recognition kütüphanesinin flac-win32.exe çağrılarında
    CREATE_NO_WINDOW (0x08000000) bayrağını zorunlu kılar.
    Bu yama yapılmazsa, mikrofondan her ses alındığında ekranda siyah bir
    CMD / Konsol penceresi yanıp söner ve ses odağını bozar.
    """
    try:
        import os
        import subprocess
        import speech_recognition as sr

        if os.name != "nt":
            return

        if getattr(sr.AudioData, "_boru_silent_patched", False):
            return

        def _silent_get_flac_data(self, convert_rate=None, convert_width=None):
            assert convert_width is None or (
                convert_width % 1 == 0 and 1 <= convert_width <= 3
            ), "Sample width to convert to must be between 1 and 3 inclusive"

            if self.sample_width > 3 and convert_width is None:
                convert_width = 3

            wav_data = self.get_wav_data(convert_rate, convert_width)
            flac_converter = sr.get_flac_converter()

            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = subprocess.SW_HIDE
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

            process = subprocess.Popen(
                [
                    flac_converter,
                    "--stdout",
                    "--totally-silent",
                    "--best",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                startupinfo=startup_info,
                creationflags=creation_flags,
            )
            flac_data, _ = process.communicate(wav_data)
            return flac_data

        sr.AudioData.get_flac_data = _silent_get_flac_data
        sr.AudioData._boru_silent_patched = True
        logger.debug("speech_recognition için sessiz FLAC yaması başarıyla uygulandı.")
    except Exception as exc:
        logger.debug(f"speech_recognition sessiz FLAC yaması uygulanamadı: {exc}")


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
                patch_speech_recognition_windows_console()
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
