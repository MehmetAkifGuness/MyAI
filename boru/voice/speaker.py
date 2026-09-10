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

    def speak(self, text: str, async_mode: bool = True) -> None:
        """Metni seslendirir."""
        if not self.enabled:
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
            try:
                # Windows PowerShell SpeechSynthesizer ile seslendirme
                escaped = text.replace("'", "''").replace('"', '""')
                ps_script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$synth.Speak('{escaped}')"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                )
            except Exception as e:
                logger.debug(f"Seslendirme başarısız oldu: {e}")
