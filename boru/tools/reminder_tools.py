from __future__ import annotations

import datetime
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ReminderItem:
    def __init__(self, item_id: int, due_at: float, label: str, timer: threading.Timer):
        self.item_id = item_id
        self.due_at = due_at
        self.label = label
        self.timer = timer


class ReminderService:
    """
    Arka planda çalışan, sesli ve bildirimli akıllı sayaç ve hatırlatıcı servisi.
    """
    _instance: Optional[ReminderService] = None

    def __init__(self):
        self._lock = threading.Lock()
        self._reminders: Dict[int, ReminderItem] = {}
        self._counter = 0

    @classmethod
    def get_instance(cls) -> ReminderService:
        if cls._instance is None:
            cls._instance = ReminderService()
        return cls._instance

    def schedule(
        self,
        seconds: float,
        label: str = "Süre doldu!",
        on_fire: Optional[Callable[[str], None]] = None,
    ) -> Tuple[int, str]:
        with self._lock:
            self._counter += 1
            item_id = self._counter
            due_at = time.time() + seconds

            def _on_timeout():
                self._trigger_fire(item_id, label, on_fire)

            timer = threading.Timer(seconds, _on_timeout)
            timer.daemon = True
            timer.start()

            item = ReminderItem(item_id, due_at, label, timer)
            self._reminders[item_id] = item

            # Zaman formatı
            if seconds >= 3600:
                hours = int(seconds // 3600)
                mins = int((seconds % 3600) // 60)
                dur_str = f"{hours} saat {mins} dakika" if mins else f"{hours} saat"
            elif seconds >= 60:
                mins = int(seconds // 60)
                secs = int(seconds % 60)
                dur_str = f"{mins} dakika {secs} saniye" if secs else f"{mins} dakika"
            else:
                dur_str = f"{int(seconds)} saniye"

            due_time_str = datetime.datetime.fromtimestamp(due_at).strftime("%H:%M:%S")
            return item_id, f"{dur_str} sonrasına ({due_time_str}) hatırlatıcı kuruldu: '{label}'."

    def _trigger_fire(
        self,
        item_id: int,
        label: str,
        custom_cb: Optional[Callable[[str], None]],
    ) -> None:
        with self._lock:
            self._reminders.pop(item_id, None)

        logger.info(f"Hatırlatıcı tetiklendi: {label}")

        # 1. İşitsel çan tonu çal
        try:
            from boru.voice.audio_cues import AudioCueService
            AudioCueService().play_success()
        except Exception:
            pass

        # 2. Sesli ikaz (TTS)
        def _speak():
            try:
                from boru.voice.speaker import VoiceOutputService
                speaker = VoiceOutputService(enabled=True)
                speaker.speak(f"Hatırlatıcı: {label}")
            except Exception as e:
                logger.debug(f"Hatırlatıcı TTS hatası: {e}")

        threading.Thread(target=_speak, daemon=True).start()

        # 3. Özel geri çağırma fonksiyonu
        if custom_cb:
            try:
                custom_cb(label)
            except Exception as e:
                logger.debug(f"Hatırlatıcı callback hatası: {e}")

    def list_active(self) -> str:
        with self._lock:
            now = time.time()
            valid = [r for r in self._reminders.values() if r.due_at > now]
            if not valid:
                return "Şu anda aktif bir hatırlatıcı veya sayaç bulunmuyor."

            lines = ["Aktif Hatırlatıcılar:"]
            for r in valid:
                remain = int(r.due_at - now)
                lines.append(f"- '{r.label}' (Kalan süre: {remain} sn)")
            return "\n".join(lines)

    def cancel_all(self) -> str:
        with self._lock:
            count = len(self._reminders)
            for r in self._reminders.values():
                r.timer.cancel()
            self._reminders.clear()
            if count > 0:
                return f"{count} adet aktif hatırlatıcı iptal edildi."
            return "İptal edilecek aktif hatırlatıcı yok."


def resolve_reminder_command(user_text: str) -> Optional[str]:
    """
    Doğal dilde hatırlatıcı ve sayaç komutlarını çözer.
    Örnekler:
    - "10 saniye sonra uyar: fırını kapat"
    - "5 dakika sonra çay hazır de"
    - "30 saniyelik sayaç başlat"
    - "aktif sayaçlar"
    - "sayaçları iptal et"
    """
    cleaned = user_text.lower().strip().strip(".!?,")
    service = ReminderService.get_instance()

    # 1. Listeleme & İptal
    if any(k in cleaned for k in ("aktif hatırlatıcı", "aktif sayaç", "hatırlatıcılar", "sayaçlar")):
        if any(c in cleaned for c in ("iptal", "sil", "temizle", "durdur")):
            return service.cancel_all()
        return service.list_active()

    if any(k in cleaned for k in ("hatırlatıcıları iptal", "sayaçları iptal", "alarmları kapat", "sayacı durdur")):
        return service.cancel_all()

    # 2. Süre Ayrıştırma (Saniye, Dakika, Saat)
    # Örnek: "10 saniye sonra ...", "5 dakika sonra ...", "1 saat sonra ..."
    match = re.search(
        r"(\d+)\s*(saniye|dakika|saat|sn|dk)?\s+(?:sonra|sonraya)\s*(?:bana\s+)?(?:hatırlat|haber ver|uyar|söyle|de)?\s*:?\s*(.*)",
        cleaned,
    )
    if match:
        val_str, unit, label = match.groups()
        val = int(val_str)
        unit = (unit or "dakika").lower()

        seconds = val
        if unit in ("dakika", "dk"):
            seconds = val * 60
        elif unit in ("saat",):
            seconds = val * 3600

        clean_label = label.strip()
        if not clean_label:
            clean_label = f"{val} {unit} süresi doldu"

        # Başındaki 'ki', 'bunu' vb. temizle
        clean_label = re.sub(r"^(?:diye|bunu|şunu)\s+", "", clean_label).strip()

        _, msg = service.schedule(seconds, clean_label)
        return msg

    # 3. Sayaç Başlatma ("30 saniyelik sayaç başlat", "5 dakikalık alarm kur")
    timer_match = re.search(r"(\d+)\s*(saniye|dakika|saat|sn|dk)(?:lik|lık)?\s+(?:sayaç|alarm|zamanlayıcı)\s*(?:kur|başlat|aç|ayarla)", cleaned)
    if timer_match:
        val_str, unit = timer_match.groups()
        val = int(val_str)
        unit = unit.lower()

        seconds = val
        if unit in ("dakika", "dk"):
            seconds = val * 60
        elif unit in ("saat",):
            seconds = val * 3600

        label = f"{val} {unit} süresi doldu"
        _, msg = service.schedule(seconds, label)
        return msg

    return None

