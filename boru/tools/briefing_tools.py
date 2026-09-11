"""
boru.tools.briefing_tools
=========================
Jarvis tarzı 'Günün Brifingi' (Executive Daily Briefing) modülü.
Kullanıcının isteğiyle hava durumu, döviz kurları, kayıtlı notlar/görevler
ve sistem donanım durumunu tek bir akıcı Türkçe konuşma çıktısında özetler.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_daily_briefing() -> str:
    """
    Canlı hava durumu, döviz kurları, bekleyen notlar ve sistem durumunu
    içeren kapsamlı ve akıcı bir sesli brifing metni üretir.
    """
    now = datetime.datetime.now()
    hour = now.hour

    if 5 <= hour < 12:
        greeting = "Günaydın efendim."
    elif 12 <= hour < 18:
        greeting = "İyi günler efendim."
    elif 18 <= hour < 23:
        greeting = "İyi akşamlar efendim."
    else:
        greeting = "İyi geceler efendim."

    parts = [greeting]

    # 1. Hava Durumu
    try:
        from boru.tools.quick_info import get_weather
        w_ok, w_text = get_weather("Ankara")
        if w_ok and w_text:
            parts.append(w_text)
    except Exception as e:
        logger.debug(f"Brifing hava durumu hatası: {e}")

    # 2. Döviz Kurları
    try:
        from boru.tools.quick_info import get_currency_rate
        c_ok, c_text = get_currency_rate("USD", "TRY")
        if c_ok and c_text:
            parts.append(c_text)
    except Exception as e:
        logger.debug(f"Brifing kur hatası: {e}")

    # 3. Bekleyen Notlar
    try:
        from boru.tools.notes_tools import NotesService
        svc = NotesService()
        notes = svc.list_notes()
        if notes:
            note_count = len(notes)
            sample_notes = [f"'{n.get('text', '')}'" for n in notes[:3]]
            sample_str = ", ".join(sample_notes)
            if note_count > 3:
                parts.append(f"Not defterinizde {note_count} adet not bulunuyor. İlk birkaçı: {sample_str}.")
            else:
                parts.append(f"Not defterinizde {note_count} adet kayıtlı notunuz var: {sample_str}.")
        else:
            parts.append("Ajandanızda bekleyen herhangi bir not bulunmuyor.")
    except Exception as e:
        logger.debug(f"Brifing not hatası: {e}")

    # 4. Sistem ve Donanım Durumu
    try:
        from boru.tools.system_tools import get_system_status
        s_ok, s_text = get_system_status()
        if s_ok and s_text:
            clean_sys = s_text.replace("Sistem Durumu: ", "").replace(" | ", ", ")
            parts.append(f"Sisteminizde {clean_sys}.")
    except Exception as e:
        logger.debug(f"Brifing sistem durumu hatası: {e}")

    parts.append("Tüm sistemler aktif ve göreve hazırım.")
    return " ".join(parts)


def resolve_briefing_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının brifing talebini algılar ve brifing raporunu döner.
    Örnek: "bana brifing ver", "günün özeti", "bugün ne var", "sabah brifingi", "günlük brifing"
    """
    cleaned = user_text.lower().strip().strip(".!?,")
    if any(
        k in cleaned
        for k in (
            "bana brifing ver",
            "brifing ver",
            "günün özeti",
            "günün özetini ver",
            "bugün ne var",
            "sabah brifingi",
            "günlük brifing",
            "günün brifingi",
            "durum brifingi",
        )
    ):
        return get_daily_briefing()

    return None
