from __future__ import annotations

import io
import logging
import math
import struct
import threading
import wave
from typing import Optional

logger = logging.getLogger(__name__)


def _generate_wav_bytes(
    freq_points: list[tuple[float, float]],
    duration: float = 0.2,
    sample_rate: int = 44100,
    volume: float = 0.25,
) -> bytes:
    """
    Saf sinüs dalgaları ve yumuşak sönümleme (exponential decay) ile
    tıklama/patlama sesi içermeyen kristal berraklığında fütüristik ses tonu sentezler.
    freq_points: [(başlangıç_frekansı, bitiş_frekansı)]
    """
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()

        for i in range(n_samples):
            t = i / sample_rate
            progress = t / duration

            # Zarif sönümleme eğrisi (başta yumuşak yükseliş, sonra pürüzsüz sönüm)
            attack = min(1.0, progress * 15)
            decay = math.exp(-3.5 * progress)
            envelope = attack * decay * volume

            sample_val = 0.0
            for start_freq, end_freq in freq_points:
                current_freq = start_freq + (end_freq - start_freq) * progress
                sample_val += math.sin(2 * math.pi * current_freq * t)

            sample_val = (sample_val / len(freq_points)) * envelope
            clamped = max(-32767, min(32767, int(sample_val * 32767)))
            frames.extend(struct.pack("<h", clamped))

        wav.writeframes(frames)

    buf.seek(0)
    return buf.read()


class AudioCueService:
    """
    Börü'nün uyandırma, dinleme başlangıcı/bitişi ve onay durumlarında
    harici dosya gerektirmeksizin zarif ses efektleri çalan servis.
    """

    def __init__(self, enabled: bool = True, volume: float = 0.25):
        self.enabled = enabled
        self.volume = volume
        self._cache: dict[str, bytes] = {}
        self._sound_cache: dict[str, any] = {}
        self._lock = threading.Lock()

    def _get_sound(self, name: str, freq_points: list[tuple[float, float]], duration: float):
        if name not in self._sound_cache:
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                wav_bytes = _generate_wav_bytes(freq_points, duration=duration, volume=self.volume)
                self._sound_cache[name] = pygame.mixer.Sound(io.BytesIO(wav_bytes))
            except Exception as e:
                logger.debug(f"AudioCue ses oluşturulamadı: {e}")
                return None
        return self._sound_cache.get(name)

    def _play_sound(self, name: str, freq_points: list[tuple[float, float]], duration: float):
        if not self.enabled:
            return

        def _worker():
            with self._lock:
                sound = self._get_sound(name, freq_points, duration)
                if sound:
                    try:
                        sound.play()
                    except Exception as e:
                        logger.debug(f"AudioCue çalma hatası: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def play_wake(self) -> None:
        """'Börü' dendiğinde çalan fütüristik çift tonlu uyanma çanı (C6 -> G6)."""
        self._play_sound("wake", [(1046.5, 1318.5), (1318.5, 1567.98)], duration=0.28)

    def play_listen_start(self) -> None:
        """Dinleme başladığında çalan yumuşak yükselen bildirim tonu."""
        self._play_sound("listen_start", [(587.33, 880.0)], duration=0.15)

    def play_listen_stop(self) -> None:
        """Kullanıcı konuştuğunda/sustuğunda çalan yumuşak alçalan tamamlama tonu."""
        self._play_sound("listen_stop", [(880.0, 587.33)], duration=0.15)

    def play_success(self) -> None:
        """Komut başarıyla yerine getirildiğinde çalan onay çanı."""
        self._play_sound("success", [(784.0, 1046.5)], duration=0.22)

    def play_error(self) -> None:
        """Anlaşılamadığında veya zaman aşımında çalan yumuşak uyarı tonu."""
        self._play_sound("error", [(392.0, 311.13)], duration=0.25)

