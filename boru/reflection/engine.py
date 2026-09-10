from __future__ import annotations

import hashlib
import time
from typing import Sequence

from boru.reflection.models import ReflectionRecord, ReflectionVerdict
from boru.reflection.repository import JsonReflectionRepository


class SelfReflectionEngine:
    """
    Görevlerin başarı, başarısızlık veya geri alma durumlarını analiz edip
    kalıcı dersler ve kurallar çıkaran öz-iyileştirme motoru.
    """

    def __init__(self, repository: JsonReflectionRepository):
        self._repository = repository

    def record_success(
        self,
        task: str,
        paths: Sequence[str],
        summary: str = "",
    ) -> ReflectionRecord:
        """Başarılı bir kodlama/iyileştirme görevinden ders kaydeder."""
        record_id = hashlib.sha256(f"pass:{task}:{time.time()}".encode()).hexdigest()[:16]
        clean_paths = tuple(paths)
        lesson_text = summary.strip() or f"'{task}' görevi {', '.join(clean_paths)} dosyalarında başarıyla doğrulandı ve uygulandı."

        record = ReflectionRecord(
            id=record_id,
            task=task,
            verdict=ReflectionVerdict.PASS,
            target_paths=clean_paths,
            lesson=lesson_text,
            timestamp=time.time(),
        )
        self._repository.save_record(record)
        return record

    def record_failure(
        self,
        task: str,
        paths: Sequence[str],
        error_or_report: str,
    ) -> ReflectionRecord:
        """Başarısız bir denemeden negatif geri bildirim ve kaçınılacak kural üretir."""
        record_id = hashlib.sha256(f"fail:{task}:{time.time()}".encode()).hexdigest()[:16]
        clean_paths = tuple(paths)
        clean_err = error_or_report.strip()
        # Çok uzun raporları ilk 300 karaktere sınırla
        short_err = clean_err[:300] + ("..." if len(clean_err) > 300 else "")
        lesson_text = f"DİKKAT: '{task}' işleminde şu hata oluştu: {short_err}. Bu yaklaşım tekrar denenmemeli."

        record = ReflectionRecord(
            id=record_id,
            task=task,
            verdict=ReflectionVerdict.FAIL,
            target_paths=clean_paths,
            lesson=lesson_text,
            timestamp=time.time(),
        )
        self._repository.save_record(record)
        return record

    def record_rollback(
        self,
        paths: Sequence[str],
        reason: str = "Kullanıcı geri alma talep etti",
    ) -> ReflectionRecord:
        """Geri alınan bir iyileştirmeden ibret dersi çıkarır."""
        record_id = hashlib.sha256(f"rollback:{','.join(paths)}:{time.time()}".encode()).hexdigest()[:16]
        clean_paths = tuple(paths)
        lesson_text = f"UYARI: {', '.join(clean_paths)} dosyalarındaki son değişiklik geri alındı ({reason}). Bu dosyalarda daha dikkatli ve kontrollü ilerlenmeli."

        record = ReflectionRecord(
            id=record_id,
            task="İyileştirmeyi geri al",
            verdict=ReflectionVerdict.ROLLBACK,
            target_paths=clean_paths,
            lesson=lesson_text,
            timestamp=time.time(),
        )
        self._repository.save_record(record)
        return record

    def get_lessons_for_targets(self, paths: tuple[str, ...]) -> list[ReflectionRecord]:
        return self._repository.query_by_paths(paths)
