from __future__ import annotations

import logging
import re
import subprocess
import threading
from typing import Sequence

logger = logging.getLogger(__name__)


class VoiceOutputService:
    """
    Börü'nün yanıtlarını Windows SAPI veya PowerShell üzerinden seslendiren servis.
    Kod bloklarını ve gereksiz etiketleri konuşmadan önce otomatik temizler.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._lock = threading.Lock()

    def stop(self) -> None:
        """Devam eden ses çalmayı anında durdurur."""
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    @staticmethod
    def clean_text_for_speech(text: str) -> str:
        """Kod bloklarını, sembolleri ve markdown etiketlerini temizler; cümleleri yarıda kesmez."""
        # <think>...</think> düşünce bloklarını çıkar
        no_think = re.sub(r"<think>[\s\S]*?</think>", "", text)
        # ```kod``` bloklarını çıkar
        no_code = re.sub(r"```[\s\S]*?```", " ilgili kod bloğu ", no_think)
        # `inline kod` bloklarını sadeleştir
        no_inline = re.sub(r"`([^`]+)`", r"\1", no_code)
        # Markdown başlıklarını, sembolleri temizle
        clean = re.sub(r"[#*_~>\[\]\(\)]", " ", no_inline)
        # URL'leri temizle
        clean = re.sub(r"https?://\S+", " bağlantı ", clean)
        # Çoklu boşlukları sadeleştir
        clean = re.sub(r"\s+", " ", clean).strip()

        # Eğer çok uzun bir metin ise (1500 karakterden fazla), en yakın cümle sonundan (.!?) zarifçe sınırla
        if len(clean) > 1500:
            truncated = clean[:1500]
            last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
            if last_period > 800:
                clean = truncated[:last_period + 1]
            else:
                clean = truncated + "..."
        return clean

    @staticmethod
    def split_into_sentences(text: str) -> list[str]:
        """Metni doğal cümle sınırlarından (nokta, ünlem, soru işareti, satır başı) böler."""
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text)
        sentences = re.split(r"(?<=[.!?\n])\s+", cleaned)
        result = []
        for s in sentences:
            s_clean = s.strip()
            if s_clean and s_clean != "ilgili kod bloğu":
                result.append(s_clean)
        return result

    def speak(self, text: str, async_mode: bool = True, force: bool = False) -> None:
        """Metni seslendirir. force=True ise sesli yanıt anahtarı kapalı olsa dahi seslendirir."""
        if not self.enabled and not force:
            return

        cleaned = self.clean_text_for_speech(text)
        if not cleaned or cleaned == "ilgili kod bloğu":
            return

        if async_mode:
            threading.Thread(target=self._speak_sync, args=(cleaned,), daemon=True).start()
        else:
            self._speak_sync(cleaned)

    def _speak_sync(self, text: str) -> None:
        with self._lock:
            sentences = self.split_into_sentences(text)
            if not sentences:
                return

            # Çoklu cümlelerde ilk cümle hemen çalarken sonraki cümleler arka planda önceden sentezlenir (Streaming TTS)
            if len(sentences) > 1:
                if self._speak_streaming_pipeline(sentences):
                    return

            # Tek cümle veya fallback
            if self._speak_neural_sync(text):
                return

            self._speak_sapi_sync(text)

    def _generate_neural_mp3(self, text: str) -> Optional[str]:
        """Tek bir metin/cümle için arka planda Edge TTS ile MP3 dosyası oluşturur."""
        try:
            import asyncio
            import tempfile
            import edge_tts

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            async def _generate():
                communicate = edge_tts.Communicate(text, voice="tr-TR-AhmetNeural")
                await communicate.save(tmp_path)

            asyncio.run(_generate())
            return tmp_path
        except Exception as err:
            logger.debug(f"Neural MP3 sentez hatası: {err}")
            return None

    def _play_single_mp3(self, tmp_path: str, text: str) -> bool:
        """Sentezlenmiş MP3 dosyasını çalar ve ardından temizler."""
        import os
        import time
        played = False
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            time.sleep(0.06)
            while pygame.mixer.music.get_busy():
                time.sleep(0.03)
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            played = True
        except Exception as e:
            logger.debug(f"pygame çalma hatası: {e}")

        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return played

    def _speak_streaming_pipeline(self, sentences: list[str]) -> bool:
        """Cümleleri kuyruğa alarak ilk cümleyi hemen çalar, diğerlerini paralel sentezler."""
        import queue

        audio_queue: queue.Queue[Optional[tuple[str, str]]] = queue.Queue(maxsize=3)
        producer_failed = False

        def _producer():
            nonlocal producer_failed
            for sent in sentences:
                tmp = self._generate_neural_mp3(sent)
                if tmp:
                    audio_queue.put((tmp, sent))
                else:
                    producer_failed = True
                    break
            audio_queue.put(None)

        prod_thread = threading.Thread(target=_producer, daemon=True)
        prod_thread.start()

        all_played = True
        while True:
            item = audio_queue.get()
            if item is None:
                break
            tmp_path, sent_text = item
            success = self._play_single_mp3(tmp_path, sent_text)
            if not success:
                all_played = False

        return all_played and not producer_failed

    def _speak_neural_sync(self, text: str) -> bool:
        """Tek parça Neural TTS seslendirme."""
        tmp_path = self._generate_neural_mp3(text)
        if not tmp_path:
            return False
        return self._play_single_mp3(tmp_path, text)

    def _speak_sapi_sync(self, text: str) -> None:
        """Windows yerel SAPI ile seslendirme (Yedek motor)."""
        try:
            import base64
            escaped = text.replace("'", "''").replace('"', '""')
            ps_script = (
                "Add-Type -AssemblyName System.Speech; "
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$synth.Speak('{escaped}')"
            )
            encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                startupinfo=startupinfo,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
        except Exception as e:
            logger.debug(f"Yerel SAPI seslendirme hatası: {e}")
