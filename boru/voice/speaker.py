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

    @staticmethod
    def clean_text_for_speech(text: str) -> str:
        """Kod bloklarını, sembolleri ve markdown etiketlerini temizler."""
        # ```kod``` bloklarını çıkar
        no_code = re.sub(r"```[\s\S]*?```", " [kod bloğu] ", text)
        # `inline kod` bloklarını çıkar
        no_inline = re.sub(r"`[^`]*`", "", no_code)
        # Markdown başlıklarını, kalın/italik işaretlerini temizle
        clean = re.sub(r"[#*_~>\[\]]", " ", no_inline)
        # URL'leri temizle
        clean = re.sub(r"https?://\S+", " bağlantı ", clean)
        # Çoklu boşlukları sadeleştir
        clean = re.sub(r"\s+", " ", clean).strip()
        # Çok uzun metinleri seslendirirken ilk 300 karaktere sınırla
        if len(clean) > 300:
            clean = clean[:300] + "..."
        return clean

    def speak(self, text: str, async_mode: bool = True, force: bool = False) -> None:
        """Metni seslendirir. force=True ise sesli yanıt anahtarı kapalı olsa dahi seslendirir."""
        if not self.enabled and not force:
            return

        cleaned = self.clean_text_for_speech(text)
        if not cleaned or cleaned == "[kod bloğu]":
            return

        if async_mode:
            threading.Thread(target=self._speak_sync, args=(cleaned,), daemon=True).start()
        else:
            self._speak_sync(cleaned)

    def _speak_sync(self, text: str) -> None:
        with self._lock:
            # 1. Öncelik: Ultra Doğal Microsoft Neural Türkçe Sesi (tr-TR-AhmetNeural)
            if self._speak_neural_sync(text):
                return

            # 2. Yedek: Yerel Windows SpeechSynthesizer
            self._speak_sapi_sync(text)

    def _speak_neural_sync(self, text: str) -> bool:
        """Microsoft Neural Türkçe yapay zeka sesi ile insan doğallığında seslendirir."""
        try:
            import asyncio
            import base64
            import os
            import tempfile
            import edge_tts

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            async def _generate():
                communicate = edge_tts.Communicate(text, voice="tr-TR-AhmetNeural")
                await communicate.save(tmp_path)

            asyncio.run(_generate())

            norm_path = tmp_path.replace("\\", "/")
            word_count = len(text.split())
            est_seconds = max(1.8, word_count * 0.38 + 0.8)

            ps_script = f"""
            Add-Type -AssemblyName PresentationCore
            $player = New-Object System.Windows.Media.MediaPlayer
            $player.Open([System.Uri]'{norm_path}')
            $player.Play()
            Start-Sleep -Milliseconds {int(est_seconds * 1000)}
            $player.Close()
            """
            encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=int(est_seconds + 10),
            )
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return True
        except Exception as err:
            logger.debug(f"Neural TTS kullanılamadı ({err}), yerel SAPI'ye geçiliyor.")
            return False

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
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        except Exception as e:
            logger.debug(f"Yerel SAPI seslendirme hatası: {e}")
