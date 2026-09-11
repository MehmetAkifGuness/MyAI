from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_NOTES_PATH = Path(__file__).resolve().parent.parent.parent / "user_notes.json"

MONTH_NAMES_TR = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
]


class NotesService:
    """
    Kullanıcının sesli ve yazılı olarak aldığı hızlı notları
    kalıcı olarak JSON dosyasında saklayan ve yöneten servis.
    """

    def __init__(self, notes_path: Path | None = None):
        self._path = notes_path or DEFAULT_NOTES_PATH

    def _load(self) -> List[Dict]:
        if not self._path.exists():
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.debug(f"Notları okuma hatası: {e}")
            return []

    def _save(self, notes: List[Dict]) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(notes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Notları kaydetme hatası: {e}")

    def add_note(self, text: str) -> Tuple[bool, str]:
        cleaned = text.strip()
        if not cleaned:
            return False, "Eklenecek not metni boş olamaz."

        notes = self._load()
        now = datetime.datetime.now()
        month_name = MONTH_NAMES_TR[now.month] if 1 <= now.month <= 12 else str(now.month)
        date_str = f"{now.day} {month_name} {now.strftime('%H:%M')}"

        note_id = len(notes) + 1
        new_entry = {
            "id": note_id,
            "timestamp": now.timestamp(),
            "date_str": date_str,
            "text": cleaned,
        }
        notes.append(new_entry)
        self._save(notes)

        return True, f"Notunuz kaydedildi: '{cleaned}'"

    def list_notes(self) -> Tuple[bool, str]:
        notes = self._load()
        if not notes:
            return True, "Kayıtlı herhangi bir notunuz bulunmuyor."

        lines = [f"Toplam {len(notes)} adet notunuz var:"]
        for idx, n in enumerate(notes, start=1):
            lines.append(f"{idx}. [{n.get('date_str', '')}] {n.get('text', '')}")

        return True, "\n".join(lines)

    def get_last_note(self) -> Tuple[bool, str]:
        notes = self._load()
        if not notes:
            return True, "Kayıtlı herhangi bir notunuz bulunmuyor."

        last = notes[-1]
        return True, f"Son notunuz: '{last.get('text', '')}' ({last.get('date_str', '')})"

    def clear_notes(self) -> Tuple[bool, str]:
        notes = self._load()
        count = len(notes)
        if count == 0:
            return True, "Temizlenecek herhangi bir not bulunmuyor."

        self._save([])
        return True, f"Tüm notlarınız ({count} adet) başarıyla temizlendi."


# Singleton örneği
_service_instance: Optional[NotesService] = None


def get_notes_service() -> NotesService:
    global _service_instance
    if _service_instance is None:
        _service_instance = NotesService()
    return _service_instance


def resolve_notes_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının not alma ve sorgulama komutlarını çözer:
    - "bunu not al: yarın toplantı var"
    - "notlarıma ekle: ekmek al"
    - "notlarımı oku", "notlarımı listele"
    - "son notum neydi"
    - "notlarımı temizle"
    """
    cleaned = user_text.lower().strip().strip(".!?,")
    service = get_notes_service()

    # 1. Not Ekleme ("... not al", "notlarıma ekle", "bunu kaydet")
    # Örnek: "bunu not al: yarın toplantı var", "not al yarın sınav var", "notlarıma ekle arabayı yıka"
    add_match = re.search(
        r"^(?:lütfen\s+)?(?:bunu\s+)?(?:not\s+(?:al|et|kaydet)|notlar(?:ım)?a\s+(?:ekle|kaydet|yaz))\s*:?\s*(.*)$",
        cleaned,
    )
    if add_match:
        content = add_match.group(1).strip()
        # "diye", "şunu" vb. ayıkla
        content = re.sub(r"^(?:diye|şunu|bunu)\s+", "", content).strip()
        if content:
            _, msg = service.add_note(content)
            return msg
        else:
            return "Ne not almamı istersiniz?"

    # Alternatif cümle sonu: "yarın toplantı var bunu not al"
    add_suffix_match = re.search(r"^(.*?)\s+(?:bunu\s+)?(?:not\s+(?:al|et|kaydet)|notlar(?:ım)?a\s+ekle)$", cleaned)
    if add_suffix_match:
        content = add_suffix_match.group(1).strip()
        if content and content not in ("lütfen", "hemen", "bunu"):
            _, msg = service.add_note(content)
            return msg

    # 2. Son Notu Sorma
    if any(k in cleaned for k in ("son notum neydi", "son aldığım not", "son not neydi", "son notumu oku", "en son notum")):
        _, msg = service.get_last_note()
        return msg

    # 3. Notları Listeleme / Okuma
    if any(k in cleaned for k in ("notlarımı oku", "notlarımı listele", "notlarımı göster", "notlarımı söyle", "tüm notlarımı oku", "hangi notlarım var")):
        _, msg = service.list_notes()
        return msg

    # 4. Notları Temizleme
    if any(k in cleaned for k in ("notlarımı temizle", "notlarımı sil", "notları temizle", "notları sil", "tüm notlarımı sil")):
        _, msg = service.clear_notes()
        return msg

    return None
