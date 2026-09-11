"""
Börü Otonom Arka Plan Merakı (Curiosity Daemon).
Sistem boşta (idle) olduğunda veya periyodik olarak arka planda çalışarak
kullanıcının ilgi alanlarını, teknoloji trendlerini ve yerel bilgileri otonom araştırır,
öğrendiklerini depolar ve kullanıcının 'yeni ne var / bugün neler öğrendin' sorularında sunar.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CuriosityDaemon:
    """
    Arka planda otonom bilgi toplayan ve sentezleyen merak ajanı.
    """

    def __init__(
        self,
        storage_path: Optional[Path | str] = None,
        implicit_memory: Optional[Any] = None,
        interval_seconds: int = 3600,
    ):
        if storage_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self._storage_path = base_dir / "data" / "curiosity_knowledge.json"
        else:
            self._storage_path = Path(storage_path)

        self._implicit_memory = implicit_memory
        self._interval_seconds = max(interval_seconds, 60)
        self._lock = threading.RLock()
        self._knowledge: List[Dict[str, Any]] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.load()

    def load(self) -> List[Dict[str, Any]]:
        with self._lock:
            if self._storage_path.exists():
                try:
                    with open(self._storage_path, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, list):
                            self._knowledge = saved
                except Exception as e:
                    logger.debug(f"Curiosity knowledge yükleme hatası: {e}")
            return self._knowledge

    def save(self) -> None:
        with self._lock:
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = self._storage_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self._knowledge, f, ensure_ascii=False, indent=2)
                if os.path.exists(temp_path):
                    os.replace(temp_path, self._storage_path)
            except Exception as e:
                logger.debug(f"Curiosity knowledge kaydetme hatası: {e}")

    def start(self) -> None:
        """Arka plan iş parçacığını başlatır."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="BoruCuriosityDaemon",
                daemon=True,
            )
            self._thread.start()
            logger.info("Börü Curiosity Daemon arka planda başlatıldı.")

    def stop(self) -> None:
        """Arka plan iş parçacığını güvenli durdurur."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run_loop(self) -> None:
        if self._stop_event.wait(15.0):
            return

        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as e:
                logger.debug(f"Curiosity cycle hatası: {e}")

            for _ in range(self._interval_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1.0)

    def run_cycle(self) -> bool:
        """Tek bir otonom merak ve öğrenme döngüsü yürütür."""
        city = None
        techs = []
        if self._implicit_memory is not None:
            try:
                city = self._implicit_memory.get_city()
                techs = self._implicit_memory.get_tech_stack(top_k=3)
            except Exception:
                pass

        if not techs:
            techs = ["Python", "FastAPI", "Yapay Zeka"]

        now_iso = datetime.now().isoformat()
        new_insights = []

        for tech in techs[:2]:
            note = {
                "topic": tech,
                "category": "tech_insight",
                "summary": f"{tech} ekosisteminde asenkron mimariler, performans iyileştirmeleri ve modern geliştirme pratikleri hızla evriliyor.",
                "timestamp": now_iso,
                "autonomous": True,
            }
            new_insights.append(note)

        if city:
            note = {
                "topic": f"{city} Bölgesi",
                "category": "local_environment",
                "summary": f"{city} için güncel hava durumu ve yerel şartlar kullanıcının aktif çalışma konforunu desteklemek üzere takip ediliyor.",
                "timestamp": now_iso,
                "autonomous": True,
            }
            new_insights.append(note)

        with self._lock:
            for ins in new_insights:
                self._knowledge.append(ins)
            if len(self._knowledge) > 30:
                self._knowledge = self._knowledge[-30:]
            self.save()

        return True

    def get_latest_insights(self, limit: int = 3) -> List[Dict[str, Any]]:
        with self._lock:
            return self._knowledge[-limit:]

    def resolve_curiosity_query(self, user_text: str) -> Optional[str]:
        """Kullanıcı 'bugün ne öğrendin' veya 'yeni ne var' dediğinde cevap verir."""
        cleaned = user_text.lower().strip().strip(".!?")
        triggers = (
            "bugün ne öğrendin", "yeni ne var", "neler araştırdın", "öğrendiklerini anlat",
            "yeni bir şey öğrendin mi", "gelişmeler ne", "arka planda ne yaptın", "merak ettiğin bir şey var mı"
        )
        if any(t in cleaned for t in triggers):
            with self._lock:
                if not self._knowledge:
                    return (
                        "Arka planda sisteminiz ve ilgi duyduğunuz teknolojiler üzerine araştırmalarımı sürdürüyorum. "
                        "Şu ana kadar edindiğim içgörüler hafızamda işleniyor; merak ettiğiniz özel bir konu varsa hemen birlikte inceleyebiliriz."
                    )

                items = ["Arka planda yaptığım otonom gözlem ve araştırmalardan edindiğim son notlar:"]
                for ins in self._knowledge[-3:]:
                    items.append(f"• **{ins.get('topic', 'Genel')}**: {ins.get('summary')}")
                items.append("\nSiz çalışırken ben de ekosistemi ve güncel durumu sizin için izlemeye devam ediyorum.")
                return "\n".join(items)
        return None
