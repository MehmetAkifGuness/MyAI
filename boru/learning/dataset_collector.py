"""
Börü İnce Ayar Veri Madencisi (Self-Training Dataset Collector).
Kullanıcı ile Börü arasındaki başarılı, kaliteli diyalogları Alpaca / ShareGPT formatında
otonom olarak toplar, hassas verileri (API key, parola) maskeler ve gelecekteki
yerel model ince ayarı (Fine-Tuning / LoRA) için data/self_training_dataset.jsonl dosyasına yazar.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DatasetCollector:
    """
    Sohbet akışından yüksek kaliteli eğitim verisi madenciliği yapan toplayıcı.
    """

    _SENSITIVE_PATTERNS = [
        (re.compile(r"\b(sk-[a-zA-Z0-9]{20,})\b"), "[REDACTED_API_KEY]"),
        (re.compile(r"\b(ghp_[a-zA-Z0-9]{20,})\b"), "[REDACTED_GITHUB_TOKEN]"),
        (re.compile(r"\b(Bearer\s+[a-zA-Z0-9_\-\.]{20,})\b", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
        (re.compile(r"\b(password|parola|şifre)\s*[:=]\s*([^\s]+)", re.IGNORECASE), r"\1: [REDACTED_PASSWORD]"),
    ]

    def __init__(self, storage_path: Optional[Path | str] = None):
        if storage_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self._storage_path = base_dir / "data" / "self_training_dataset.jsonl"
        else:
            self._storage_path = Path(storage_path)

        self._lock = threading.RLock()
        self._last_user_message = ""
        self._last_assistant_message = ""

    def _sanitize(self, text: str) -> str:
        res = text
        for pat, repl in self._SENSITIVE_PATTERNS:
            res = pat.sub(repl, res)
        return res

    def observe(self, user_message: str) -> None:
        """MessageObserver uyumluluğu."""
        pass

    def observe_turn(self, user_message: str, assistant_message: str) -> None:
        """
        TurnObserver protokolü: Her turda geçerli ve kaliteli bir etkileşim varsa
        veri setine yazar.
        """
        user_text = user_message.strip()
        asst_text = assistant_message.strip()

        if not user_text or not asst_text:
            return

        if len(user_text) < 3 or len(asst_text) < 5:
            return

        if asst_text.startswith("Hata:") or "Dil modeli boş yanıt döndürdü" in asst_text:
            return

        correction_words = ("yanlış kelime", "öyle değil", "bunu kastetmedim", "hatalı", "seni düzeltiyorum")
        if any(w in user_text.lower() for w in correction_words):
            return

        clean_user = self._sanitize(user_text)
        clean_asst = self._sanitize(asst_text)

        category = "general_chat"
        low = clean_user.lower()
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in ("kod", "python", "fonksiyon", "hata", "test", "class", "def", "api", "backend", "frontend")):
            category = "coding"
        elif any(re.search(rf"\b{re.escape(w)}\b", low) for w in ("hava", "saat", "tarih", "kur", "dolar", "altın")):
            category = "quick_info"
        elif any(re.search(rf"\b{re.escape(w)}\b", low) for w in ("aç", "kapat", "ses", "masaüstü", "çalıştır")):
            category = "system_tools"

        entry = {
            "instruction": clean_user,
            "input": "",
            "output": clean_asst,
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "quality_score": 1.0,
        }

        with self._lock:
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._storage_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug(f"Dataset kaydetme hatası: {e}")

    def get_dataset_stats(self) -> Dict[str, Any]:
        """Kayıtlı veri seti istatistiklerini hesaplar."""
        with self._lock:
            if not self._storage_path.exists():
                return {"total_samples": 0, "categories": {}}

            count = 0
            categories: Dict[str, int] = {}
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        count += 1
                        try:
                            obj = json.loads(line)
                            cat = obj.get("category", "general")
                            categories[cat] = categories.get(cat, 0) + 1
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Dataset okuma hatası: {e}")

            return {
                "total_samples": count,
                "categories": categories,
                "file_path": str(self._storage_path),
            }
