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
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008  # DETACHED_PROCESS

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
                close_fds=True,
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
                    self._recognizer.pause_threshold = 2.0  # Cümle içi doğal nefes ve düşünme duraklaması payı
                    self._recognizer.non_speaking_duration = 1.5  # Cümlenin son kelimesini kırpmaması için sondaki ses tamponu
                    self._recognizer.phrase_threshold = 0.2
                    self._recognizer.dynamic_energy_threshold = False  # Uzun cümlelerde eşiğin yapay yükselip son kelimeyi yutmasını engeller
                    self._recognizer.energy_threshold = 200  # İnsan sesi için ideal hassasiyet eşiği
                if self._microphone is None:
                    self._microphone = sr.Microphone()
                self._initialized = True
            except Exception as e:
                logger.error(f"Mikrofon veya SpeechRecognition başlatılamadı: {e}")
                raise RuntimeError(f"Ses tanıma motoru başlatılamadı: {e}")

    def _recognize_offline_fallback(self, audio) -> Optional[str]:
        """Çevrimdışı yerel Whisper modeli kuruluysa sesi yerel olarak transkribe eder."""
        try:
            from faster_whisper import WhisperModel
            import tempfile
            import os

            if getattr(self, "_offline_model", None) is None:
                self._offline_model = WhisperModel("tiny", device="cpu", compute_type="int8")

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
                f.write(audio.get_wav_data())

            segments, _ = self._offline_model.transcribe(wav_path, language="tr")
            text = " ".join([seg.text for seg in segments]).strip()

            try:
                os.remove(wav_path)
            except Exception:
                pass

            return text if text else None
        except Exception as e:
            logger.debug(f"Çevrimdışı ses tanıma hatası: {e}")
            return None

    def listen_once(self, timeout: float = 8.0, phrase_time_limit: float = 60.0, adjust_noise: bool = False) -> str:
        """
        Mikrofonu dinler ve konuşulan metni Türkçe olarak döndürür.
        Çevrimiçi Google STT önceliklidir; internet kesintisinde yerel Whisper'a otomatik geçer.
        """
        self._ensure_init()
        import speech_recognition as sr

        try:
            with self._microphone as source:
                if adjust_noise:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    eth = getattr(self._recognizer, "energy_threshold", None)
                    if isinstance(eth, (int, float)):
                        self._recognizer.energy_threshold = min(max(eth, 150), 300)
                audio = self._recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )

            try:
                text = self._recognizer.recognize_google(audio, language=self.language)
                return text.strip()
            except sr.RequestError as req_err:
                offline_text = self._recognize_offline_fallback(audio)
                if offline_text:
                    logger.info("İnternet kesintisi: Çevrimdışı yerel Whisper ile ses tanındı.")
                    return offline_text
                raise RuntimeError(f"Ses tanıma servisine ulaşılamadı: {req_err}")

        except sr.WaitTimeoutError:
            raise TimeoutError("Herhangi bir ses algılanamadı (zaman aşımı).")
        except sr.UnknownValueError:
            raise ValueError("Söylenen anlaşılamadı, lütfen tekrar edin.")
