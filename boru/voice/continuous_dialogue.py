from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

STOP_PHRASES = {
    "kapat",
    "tamamdır",
    "tamam",
    "teşekkürler",
    "teşekkür ederim",
    "görüşürüz",
    "hoşça kal",
    "hoşçakal",
    "sus",
    "dur",
    "iptal",
    "çıkış",
    "çık",
}


def is_stop_phrase(text: str) -> bool:
    cleaned = text.lower().strip().strip(".!?,")
    if cleaned in STOP_PHRASES:
        return True
    for phrase in STOP_PHRASES:
        if cleaned.startswith(phrase) or cleaned.endswith(phrase):
            return True
    return False


WAKE_WORDS = {
    "börü",
    "boru",
    "hey börü",
    "hey boru",
    "ey börü",
    "ey boru",
    "alo börü",
    "börü dinle",
}


def parse_wake_word(text: str) -> tuple[bool, str]:
    """
    Kullanıcının 'Börü' veya 'Hey Börü' deyip demediğini tespit eder.
    Dönüş: (is_wake_word_detected, remaining_command)
    Örnek:
      'Börü' -> (True, '')
      'Hey Börü nasılsın' -> (True, 'nasılsın')
      'Python kodunu açıkla' -> (False, 'Python kodunu açıkla')
    """
    cleaned = text.strip()
    low = cleaned.lower()

    for w in sorted(WAKE_WORDS, key=len, reverse=True):
        if low == w or low in (f"{w}!", f"{w}?", f"{w}."):
            return True, ""
        if low.startswith(w + " ") or low.startswith(w + ",") or low.startswith(w + ":"):
            remaining = cleaned[len(w):].lstrip(" ,:!?.")
            return True, remaining

    return False, cleaned


class ContinuousVoiceController:
    """
    Jarvis benzeri 'Hands-Free' (Dokunmadan) Kesintisiz Sesli Diyalog Kontrolcüsü.
    Kullanıcı sustuğunda Börü yanıt verir, seslendirir ve tekrar konuşmayı
    dinlemek için mikrofonu otomatik olarak açar.
    """

    def __init__(
        self,
        voice_input,
        voice_output,
        on_user_speech: Callable[[str], str],
        on_status_change: Optional[Callable[[str, str], None]] = None,
        on_dialogue_ended: Optional[Callable[[], None]] = None,
    ):
        self._voice_input = voice_input
        self._voice_output = voice_output
        self._on_user_speech = on_user_speech
        self._on_status_change = on_status_change
        self._on_dialogue_ended = on_dialogue_ended

        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_active(self) -> bool:
        return self._running

    def start(self) -> None:
        """Kesintisiz diyalog döngüsünü başlatır."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._dialogue_loop,
            daemon=True,
            name="ContinuousVoiceDialogueThread",
        )
        self._thread.start()
        logger.info("Kesintisiz sesli sohbet modu başlatıldı.")

    def stop(self) -> None:
        """Diyalog döngüsünü durdurur."""
        if not self._running:
            return

        self._running = False
        self._set_status("🟢 Hazır", "#48bb78")
        if self._on_dialogue_ended:
            try:
                self._on_dialogue_ended()
            except Exception as e:
                logger.debug(f"on_dialogue_ended hatası: {e}")
        logger.info("Kesintisiz sesli sohbet modu durduruldu.")

    def _set_status(self, text: str, color: str) -> None:
        if self._on_status_change:
            try:
                self._on_status_change(text, color)
            except Exception:
                pass

    def _dialogue_loop(self) -> None:
        consecutive_timeouts = 0

        try:
            while self._running:
                self._set_status("🎙️ Dinliyor (Konuşun)...", "#ecc94b")

                try:
                    text = self._voice_input.listen_once(timeout=8.0, phrase_time_limit=15.0)
                    consecutive_timeouts = 0
                except TimeoutError:
                    consecutive_timeouts += 1
                    if consecutive_timeouts >= 2:
                        self._set_status("💤 Zaman Aşımı", "#718096")
                        self._voice_output.speak(
                            "Sizi duyamadım, dinlemeyi sonlandırıyorum.",
                            async_mode=False,
                            force=True,
                        )
                        break
                    continue
                except ValueError:
                    # Söylenen anlaşılamadı
                    self._set_status("❓ Anlaşılamadı", "#f56565")
                    continue
                except Exception as e:
                    logger.debug(f"Ses tanıma döngü hatası: {e}")
                    break

                if not text or not self._running:
                    continue

                # Kapatma / teşekkür komutu kontrolü
                if is_stop_phrase(text):
                    self._set_status("👋 Görüşmek Üzere", "#48bb78")
                    self._voice_output.speak(
                        "Rica ederim, istediğiniz zaman buradayım.",
                        async_mode=False,
                        force=True,
                    )
                    break

                # Börü Uyandırma Kelimesi Kontrolü ("Börü" veya "Hey Börü ...")
                is_wake, remaining_cmd = parse_wake_word(text)
                if is_wake:
                    if not remaining_cmd:
                        self._set_status("🐺 Dinliyorum...", "#ecc94b")
                        self._voice_output.speak(
                            "Dinliyorum, buyrun!",
                            async_mode=False,
                            force=True,
                        )
                        time.sleep(0.3)
                        continue
                    else:
                        text = remaining_cmd

                # 1. Asistan Yanıtı Üret
                self._set_status("⚡ Börü Düşünüyor...", "#3182ce")
                try:
                    reply = self._on_user_speech(text)
                except Exception as err:
                    reply = f"Bir hata oluştu: {err}"

                if not self._running:
                    break

                # 2. Yanıtı Seslendir (Konuşma bitene kadar bekle)
                self._set_status("🔊 Börü Konuşuyor...", "#48bb78")
                self._voice_output.speak(reply, async_mode=False, force=True)

                # Mikrofonun kendi hoparlör yankısını yakalamaması için kısa bekleme
                time.sleep(0.4)

        finally:
            self._running = False
            self._set_status("🟢 Hazır", "#48bb78")
            if self._on_dialogue_ended:
                try:
                    self._on_dialogue_ended()
                except Exception:
                    pass

