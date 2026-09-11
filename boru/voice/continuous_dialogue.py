from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

STOP_PHRASES = {
    "kapat",
    "börü kapat",
    "sohbeti kapat",
    "kendini kapat",
    "sesli modu kapat",
    "dinlemeyi durdur",
    "görüşürüz",
    "hoşça kal",
    "hoşçakal",
    "bay bay",
    "baybay",
    "iyi günler",
    "iyi akşamlar",
    "iyi geceler",
    "bu kadar yeterli",
    "tamamdır teşekkürler",
    "teşekkürler kapat",
    "teşekkürler kapatabilirsin",
    "teşekkürler",
    "teşekkür ederim",
    "dur",
    "börü dur",
    "sus",
    "börü sus",
    "yeterli",
    "bu kadar",
    "sonlandır",
    "çık",
    "çıkış",
}


def is_stop_phrase(text: str) -> bool:
    """
    Kullanıcının diyaloğu sonlandırmak isteyip istemediğini kontrol eder.
    'tamam', 'tamamdır' veya 'tamam şimdi şunu yapalım' gibi geçiş ifadeleri
    diyaloğu KESİNLİKLE KAPATMAZ. Yalnızca net ve kısa kapatma/vedalaşma
    cümleleri kabul edilir.
    """
    cleaned = text.lower().strip().strip(".!?,")
    words = cleaned.split()

    # Kullanıcı 4 kelimeden uzun bir cümle kurmuşsa (örn: "tamam şimdi fonksiyonu test et") kapatma değildir
    if len(words) > 4:
        return False

    # "tamam" veya "tamamdır" tek başına kapatma DEĞİLDİR; kullanıcı onay veriyordur
    if cleaned in ("tamam", "tamamdır", "ok", "peki"):
        return False

    if cleaned in STOP_PHRASES:
        return True

    for phrase in STOP_PHRASES:
        if cleaned == phrase or cleaned == f"börü {phrase}":
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
    Kullanıcının 'Börü' veya 'Hey Börü' deyip demediğini esnekçe tespit eder.
    Başta, sonda veya selam/hitap ekleriyle birlikte kullanımı destekler:
      'Börü' -> (True, '')
      'Hey Börü nasılsın' -> (True, 'nasılsın')
      'Selam Börü hava durumu nasıl' -> (True, 'hava durumu nasıl')
      'Hava durumu nasıl Börü' -> (True, 'Hava durumu nasıl')
      'Python kodunu açıkla' -> (False, 'Python kodunu açıkla')
    """
    cleaned = text.strip()
    low = cleaned.lower().strip(".!?, ")
    prefixes = ("hey", "ey", "alo", "selam", "merhaba")
    wake_bases = ("börü", "boru")

    # 1. Tam eşleşme ("börü", "hey börü", "merhaba börü" vb.)
    for base in wake_bases:
        if low == base:
            return True, ""
        for p in prefixes:
            if low == f"{p} {base}":
                return True, ""

    # 2. Başta yer alan uyandırma kelimesi ("börü ...", "hey börü ...", "merhaba börü ...")
    for pfx in ("", *(f"{p} " for p in prefixes)):
        for base in wake_bases:
            lead = f"{pfx}{base}"
            if low.startswith(lead + " ") or low.startswith(lead + ",") or low.startswith(lead + ":"):
                rem = cleaned[len(lead):].lstrip(" ,:!?.")
                return True, rem

    # 3. Sonda yer alan uyandırma kelimesi ("nasılsın börü", "hava nasıl boru")
    for base in wake_bases:
        if low.endswith(" " + base):
            rem = cleaned[:-len(base)].rstrip(" ,:!?.")
            return True, rem

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
        audio_cues: Optional[Any] = None,
    ):
        self._voice_input = voice_input
        self._voice_output = voice_output
        self._on_user_speech = on_user_speech
        self._on_status_change = on_status_change
        self._on_dialogue_ended = on_dialogue_ended
        self._audio_cues = audio_cues

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        return self._running

    def start(self) -> None:
        """Kesintisiz diyalog döngüsünü başlatır."""
        with self._lock:
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
        with self._lock:
            if not self._running:
                return

            self._running = False
            if hasattr(self._voice_output, "stop"):
                self._voice_output.stop()
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
        consecutive_unknowns = 0
        consecutive_errors = 0

        # Mikrofonun arka plan dinleyicisinden tamamen serbest kalması için kısa bekleme payı
        time.sleep(0.2)

        try:
            while self._running:
                self._set_status("🎙️ Dinliyor (Konuşun)...", "#ecc94b")
                if self._audio_cues:
                    self._audio_cues.play_listen_start()
                    time.sleep(0.12)

                try:
                    text = self._voice_input.listen_once(timeout=10.0, phrase_time_limit=45.0)
                    consecutive_timeouts = 0
                    consecutive_unknowns = 0
                    consecutive_errors = 0
                    if self._audio_cues:
                        self._audio_cues.play_listen_stop()
                except TimeoutError:
                    consecutive_timeouts += 1
                    if consecutive_timeouts >= 3:
                        self._set_status("💤 Zaman Aşımı", "#718096")
                        self._voice_output.speak(
                            "Sizi duyamadım, dinlemeyi sonlandırıyorum.",
                            async_mode=False,
                            force=True,
                        )
                        break
                    continue
                except ValueError:
                    # Söylenen anlaşılamadı (gürültü veya belirsiz fısıltı)
                    consecutive_unknowns += 1
                    self._set_status("❓ Anlaşılamadı", "#f56565")
                    if self._audio_cues:
                        self._audio_cues.play_error()
                    if consecutive_unknowns >= 2:
                        self._voice_output.speak(
                            "Sizi tam anlayamadım, lütfen tekrar eder misiniz?",
                            async_mode=False,
                            force=True,
                        )
                        consecutive_unknowns = 0
                    else:
                        time.sleep(0.3)
                    continue
                except Exception as e:
                    consecutive_errors += 1
                    logger.warning(f"Ses tanıma döngü hatası ({consecutive_errors}/3): {e}")
                    self._set_status("⚠️ Bağlantı hatası...", "#f56565")
                    if consecutive_errors >= 3:
                        self._voice_output.speak(
                            "Ses bağlantısında bir sorun oluştu, dinleme sonlandırıldı.",
                            async_mode=False,
                            force=True,
                        )
                        break
                    time.sleep(1.0)
                    continue

                if not text or not self._running:
                    continue

                # Kapatma / teşekkür komutu kontrolü
                if is_stop_phrase(text):
                    self._set_status("👋 Görüşmek Üzere", "#48bb78")
                    self._voice_output.speak(
                        "Rica ederim, istediğiniz zaman buradayım. Görüşmek üzere!",
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

