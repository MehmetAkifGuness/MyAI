from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

VOICE_AHMET = "tr-TR-AhmetNeural"
VOICE_EMEL = "tr-TR-EmelNeural"


class VoiceOutputService:
    """
    Börü'nün yanıtlarını Edge TTS (Ultra-Doğal Neural Ses) veya Windows SAPI üzerinden seslendiren servis.
    - Çoklu ses desteği: Ahmet (Erkek) ve Emel (Kadın)
    - 0 gecikmeli disk ses önbelleği (Audio Caching)
    - Cümle bazlı akışkan seslendirme (Streaming TTS)
    - Çevrimdışı SAPI fallback
    """

    def __init__(
        self,
        enabled: bool = True,
        voice: str = VOICE_AHMET,
        rate: str = "+0%",
        cache_dir: Optional[str | Path] = None,
    ):
        self.enabled = enabled
        self.voice = voice
        self.rate = rate
        self._lock = threading.Lock()

        # Ses önbellek dizini
        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            self._cache_dir = Path(tempfile.gettempdir()) / "boru_voice_cache"
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def set_voice(self, voice_name: str) -> str:
        """Aktif konuşma sesini değiştirir."""
        v_low = voice_name.lower().strip()
        if any(k in v_low for k in ("emel", "kadın", "bayan", "female")):
            self.voice = VOICE_EMEL
            return "Emel (Doğal Türkçe Kadın Sesi)"
        else:
            self.voice = VOICE_AHMET
            return "Ahmet (Doğal Türkçe Erkek Sesi)"

    def toggle_voice(self) -> str:
        """Ahmet ve Emel sesleri arasında geçiş yapar."""
        if self.voice == VOICE_AHMET:
            return self.set_voice("emel")
        else:
            return self.set_voice("ahmet")

    def get_current_voice(self) -> str:
        """Mevcut aktif sesin adını döner."""
        return "Emel (Kadın Sesi)" if "emel" in self.voice.lower() else "Ahmet (Erkek Sesi)"

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

    def _get_cache_file(self, text: str) -> Path:
        """Metin ve ses parametrelerine göre benzersiz önbellek dosya yolunu üretir."""
        h = hashlib.sha256(f"{self.voice}:{self.rate}:{text.strip()}".encode("utf-8")).hexdigest()[:16]
        return self._cache_dir / f"tts_{h}.mp3"

    def _generate_neural_mp3(self, text: str) -> Optional[str]:
        """Metin için Edge TTS ile MP3 oluşturur; önbellekte varsa hemen döner."""
        cache_file = self._get_cache_file(text)
        if cache_file.exists() and cache_file.stat().st_size > 100:
            return str(cache_file)

        try:
            import edge_tts

            async def _gen():
                communicate = edge_tts.Communicate(text, voice=self.voice, rate=self.rate)
                await communicate.save(str(cache_file))

            asyncio.run(_gen())
            if cache_file.exists() and cache_file.stat().st_size > 100:
                return str(cache_file)
        except Exception as err:
            logger.debug(f"Neural MP3 sentez hatası ({self.voice}): {err}")

        # Eğer önbellek dizinine yazılamadıysa temp dosya dene
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            async def _gen_tmp():
                communicate = edge_tts.Communicate(text, voice=self.voice, rate=self.rate)
                await communicate.save(tmp_path)

            asyncio.run(_gen_tmp())
            return tmp_path
        except Exception as e:
            logger.debug(f"Neural temp MP3 sentez hatası: {e}")
            return None

    def _play_single_mp3(self, mp3_path: str, text: str) -> bool:
        """Sentezlenmiş MP3 dosyasını çalar; geçici ise temizler, önbellekteyse korur."""
        played = False
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(mp3_path)
            pygame.mixer.music.play()
            time.sleep(0.06)
            while pygame.mixer.music.get_busy():
                time.sleep(0.03)
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            played = True
        except Exception as e:
            logger.debug(f"pygame çalma hatası: {e}")

        # Yalnızca önbellekte olmayan tek kullanımlık geçici dosyaları temizle
        try:
            p = Path(mp3_path)
            if self._cache_dir not in p.parents and p.exists():
                os.remove(mp3_path)
        except Exception:
            pass
        return played

    def _speak_sync(self, text: str) -> None:
        with self._lock:
            sentences = self.split_into_sentences(text)
            if not sentences:
                return

            # Çoklu cümlelerde ilk cümle hemen çalarken sonrakiler paralel sentezlenir (Streaming TTS)
            if len(sentences) > 1:
                if self._speak_streaming_pipeline(sentences):
                    return

            # Tek cümle veya neural konuşma
            if self._speak_neural_sync(text):
                return

            # İnternet yoksa veya neural motor hata verirse SAPI fallback
            self._speak_sapi_sync(text)

    def _speak_streaming_pipeline(self, sentences: list[str]) -> bool:
        """Cümleleri kuyruğa alarak ilk cümleyi hemen çalar, diğerlerini paralel sentezler."""
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
        """Windows yerel SAPI ile seslendirme (Çevrimdışı yedek motor)."""
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
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000008
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                startupinfo=startupinfo,
                creationflags=creationflags,
                close_fds=True,
            )
        except Exception as e:
            logger.debug(f"Yerel SAPI seslendirme hatası: {e}")


_GLOBAL_SPEAKER: Optional[VoiceOutputService] = None


def get_voice_output_service(enabled: bool = True) -> VoiceOutputService:
    global _GLOBAL_SPEAKER
    if _GLOBAL_SPEAKER is None:
        _GLOBAL_SPEAKER = VoiceOutputService(enabled=enabled)
    return _GLOBAL_SPEAKER


def resolve_voice_settings_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının Türkçe doğal dildeki ses tercihlerini ve profilini yönetir.
    Örnek: 'sesini değiştir', 'kadın sesine geç', 'erkek sesi yap', 'ses durumu'
    """
    cleaned = user_text.lower().strip().strip(".!?,")
    speaker = get_voice_output_service()

    if any(k in cleaned for k in (
        "sesini değiştir", "ses tonunu değiştir", "farklı bir sese geç",
        "başka bir sesle konuş", "sesi değiştir", "ses değiştir"
    )):
        new_name = speaker.toggle_voice()
        msg = f"Ses profilimi değiştirdim. Şu an {new_name} ile konuşuyorum."
        speaker.speak(msg)
        return msg

    if any(k in cleaned for k in (
        "kadın sesine geç", "kadın sesi yap", "bayan sesine geç", "bayan sesi yap",
        "emel sesine geç", "emel sesini aç", "kadın sesi olsun", "kadın sesine dön"
    )):
        speaker.set_voice("emel")
        msg = "Sesim Emel olarak ayarlandı. Size bu sesle eşlik etmekten mutluluk duyarım!"
        speaker.speak(msg)
        return msg

    if any(k in cleaned for k in (
        "erkek sesine geç", "erkek sesi yap", "ahmet sesine geç", "ahmet sesini aç",
        "erkek sesi olsun", "erkek sesine dön"
    )):
        speaker.set_voice("ahmet")
        msg = "Sesim Ahmet olarak ayarlandı. Emrinizdeyim, nasıl yardımcı olabilirim?"
        speaker.speak(msg)
        return msg

    if any(k in cleaned for k in (
        "hangi sesi kullanıyorsun", "ses durumu", "ses ayarı", "aktif sesin ne", "ses ayarları"
    )):
        cur = speaker.get_current_voice()
        return f"Şu anda aktif olan ses motorum: {cur} ({speaker.voice}). İsterseniz 'kadın sesine geç' veya 'erkek sesine geç' diyerek değiştirebilirsiniz."

    return None
