"""
Börü Hatalardan ve Düzeltmelerden Ders Çıkarma Motoru (Self-Reflection Learner).
Kullanıcı bir cevabı düzelttiğinde ("yanlış kelimeyi aldın", "öyle değil", "bunu kastetmedim")
yapılan hatayı otonom analiz eder, çıkarılan dersi davranış kuralı olarak kaydeder ve
gelecekteki tüm yanıtlara enjekte ederek aynı hatanın tekrarlanmasını önler.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SelfReflectionLearner:
    """
    Kullanıcı geri bildirimlerinden ders çıkaran,
    davranış kuralları oluşturan ve model bağlamına enjekte eden yansıma motoru.
    """

    _CORRECTION_TRIGGERS = [
        re.compile(r"\b(?:yanlış\s+(?:kelimeyi|anladın|yaptın|çıkarım|bilgi|cevap|aldın|şarkı|müzik|şey|şeyi))\b", re.IGNORECASE),
        re.compile(r"\b(?:öyle\s+(?:değil|demedim|kastetmedim|istememiştim))\b", re.IGNORECASE),
        re.compile(r"\b(?:bunu\s+(?:kastetmedim|demedim|sormadım|söylemedim|istemedim))\b", re.IGNORECASE),
        re.compile(r"\b(?:hatalı(?:sın|dır|ydı)?)\b", re.IGNORECASE),
        re.compile(r"\b(?:seni\s+düzeltiyorum|düzeltme\s+yapıyorum)\b", re.IGNORECASE),
        re.compile(r"\b(?:hayır\s+öyle\s+değil|yanlış\s+anlaşıldı)\b", re.IGNORECASE),
        re.compile(r"\b(?:ben\s+(?:sana|ondan)\s+bahsetmedim)\b", re.IGNORECASE),
        re.compile(r"\b(?:ne\s+alaka|alakası\s+yok)\b", re.IGNORECASE),
        re.compile(r"\b(?:çalmadı|çalmıyor|açılmadı|çalışmadı|oynamadı|ses\s+gelmiyor)\b", re.IGNORECASE),
        re.compile(r"\b(?:(?:bunu\s+)?(?:aramam|araman|açman|çalman)\s+için\s+(?:söylemedim|demedim))\b", re.IGNORECASE),
        re.compile(r"\b(?:arama\s+(?:yap\s+demedim|yapma|yapmanı\s+istemedim|demedim))\b", re.IGNORECASE),
        re.compile(r"\b(?:bu\s+bir\s+(?:sorun|hata|problem))\b", re.IGNORECASE),
        re.compile(r"\b(?:böyle\s+olsun\s+dememiştim|böyle\s+istememiştim)\b", re.IGNORECASE),
    ]

    def __init__(self, storage_path: Optional[Path | str] = None):
        if storage_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self._storage_path = base_dir / "data" / "reflection_rules.json"
        else:
            self._storage_path = Path(storage_path)

        self._lock = RLock()
        self._rules: List[Dict[str, Any]] = []
        self._last_turn: Optional[Tuple[str, str]] = None
        self.load()

    def load(self) -> List[Dict[str, Any]]:
        with self._lock:
            if self._storage_path.exists():
                try:
                    with open(self._storage_path, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, list):
                            self._rules = saved
                except Exception as e:
                    logger.debug(f"Reflection kuralları yükleme hatası: {e}")
            return self._rules

    def save(self) -> None:
        with self._lock:
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = self._storage_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self._rules, f, ensure_ascii=False, indent=2)
                if os.path.exists(temp_path):
                    os.replace(temp_path, self._storage_path)
            except Exception as e:
                logger.debug(f"Reflection kuralları kaydetme hatası: {e}")

    def observe(self, user_message: str) -> None:
        """MessageObserver uyumluluğu."""
        pass

    def observe_turn(self, user_message: str, assistant_message: str) -> None:
        """TurnObserver protokolü: Her turda düzeltme var mı bakar, önceki turun dersini çıkarır."""
        user_text = user_message.strip()
        if not user_text:
            return

        with self._lock:
            is_correction = any(p.search(user_text) for p in self._CORRECTION_TRIGGERS)

            if is_correction and self._last_turn is not None:
                prev_user, prev_asst = self._last_turn
                self._synthesize_lesson(user_text, prev_user, prev_asst)

            self._last_turn = (user_text, assistant_message.strip())

    def _synthesize_lesson(self, correction_text: str, prev_user: str, prev_asst: str) -> None:
        """Hatanın doğasını analiz edip özlü bir davranış kuralına dönüştürür."""
        corr_lower = correction_text.lower()
        prev_user_lower = prev_user.lower()
        prev_asst_lower = prev_asst.lower()

        rule_type = "general_correction"
        trigger = prev_user.strip()
        lesson = ""

        # Durum 1: Sohbet dolgusu / yanlış kelime alma ("bakacağız", "görürüz", "yaparız")
        if "yanlış kelime" in corr_lower or "kelimeyi aldı" in corr_lower:
            rule_type = "intent_overtrigger"
            trigger = prev_user.strip()
            lesson = (
                f"Kullanıcı '{prev_user}' veya benzeri genel konuşma ifadeleri söylediğinde, "
                "bunu bağımsız bir eylem/komut emri olarak algılama; genel sohbet bağlamında değerlendir."
            )

        # Durum 2: Eleştiri, Şikayet ve Hata Bildirimi ("şarkı çalmadı", "bunu araman için söylemedim" vb.)
        elif any(w in corr_lower for w in ("çalmadı", "çalmıyor", "açılmadı", "çalışmadı", "arama yap demedim", "araman için", "aramam için", "böyle olsun dememiştim", "bu bir sorun")):
            rule_type = "intent_separation_feedback"
            trigger = "feedback_criticism_separation"
            lesson = (
                "Kullanıcı eleştiri, şikayet veya hata bildirdiğinde ('şarkı çalmadı', 'bunu araman için söylemedim' vb.) "
                "bu girdiyi asla bir arama veya komut olarak yürütme; hatayı kabul et ve kibarca yardım teklif et."
            )

        # Durum 3: Hava durumu veya şehir karışıklığı ("anki", "zaman", "bugün" vs.)
        elif any(w in prev_asst_lower for w in ("anki", "hava durumu", "zaman için")) and any(w in corr_lower for w in ("derece", "bahsettim", "kastetmedim", "anladın")):
            rule_type = "entity_disambiguation"
            trigger = "hava_durumu_zaman_ekleri"
            lesson = (
                "Hava durumu veya bilgi sorgularında 'şu anki', 'anki', 'zaman' gibi zaman belirteçleri "
                "kesinlikle şehir veya konum ismi olarak algılanmamalıdır."
            )

        # Durum 4: Doğal dil düzeltmesi
        else:
            rule_type = "user_preference_correction"
            lesson = (
                f"Kullanıcı '{prev_user}' ifadesine verilen yanıta itiraz etti ('{correction_text}'). "
                f"Bu tarz girdilerde doğrudan cevaba odaklan, varsayımlardan kaçın."
            )

        exists = False
        for r in self._rules:
            if r.get("lesson") == lesson or (r.get("trigger_pattern") == trigger and r.get("rule_type") == rule_type):
                r["confidence"] = min(r.get("confidence", 1.0) + 0.5, 3.0)
                r["last_updated"] = datetime.now().isoformat()
                exists = True
                break

        if not exists:
            new_rule = {
                "id": str(uuid.uuid4())[:8],
                "rule_type": rule_type,
                "trigger_pattern": trigger,
                "lesson": lesson,
                "user_correction": correction_text,
                "confidence": 1.0,
                "created_at": datetime.now().isoformat(),
            }
            self._rules.append(new_rule)
            if len(self._rules) > 20:
                self._rules.pop(0)

            logger.info(f"Yeni davranış kuralı öğrenildi: {lesson}")

        self.save()

    def get_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._rules)

    def build_context(self, user_message: str = "") -> str:
        """AssistantContextProvider uyumlu bağlam üreticisi."""
        with self._lock:
            if not self._rules:
                return ""

            rule_lines = []
            for idx, r in enumerate(self._rules[-10:], 1):
                rule_lines.append(f"{idx}. {r.get('lesson')}")

            rules_str = "\n".join(rule_lines)
            return (
                f"[Öğrenilmiş Düzeltmeler ve Hata Önleme Kuralları]:\n"
                f"Aşağıdaki kurallar kullanıcının daha önceki düzeltmelerinden öğrenilmiştir; aynı hataları tekrarlama:\n"
                f"{rules_str}"
            )

    def resolve_rules_query(self, user_text: str) -> Optional[str]:
        """Kullanıcı 'hatalarından ne öğrendin' veya 'kuralların neler' dediğinde açıklar."""
        lower = user_text.lower().strip().strip(".!?")
        if any(k in lower for k in (
            "hatalarından ne öğrendin", "neler öğrendin", "benden ne öğrendin",
            "öğrendiğin kurallar", "hafızandaki kurallar", "nasıl ders çıkardın"
        )):
            with self._lock:
                if not self._rules:
                    return "Henüz sizden öğrendiğim özel bir düzeltme kuralı bulunmuyor; ancak sohbetimiz sırasında yaptığınız tüm düzeltmeleri anında ders çıkararak hafızama kaydediyorum."

                lines = ["Sizinle konuşurken yaptığınız düzeltmelerden çıkardığım bazı temel dersler:"]
                for idx, r in enumerate(self._rules[-5:], 1):
                    lines.append(f"{idx}. {r.get('lesson')}")
                lines.append("\nBu kuralları her yanıtımda dikkate alarak kendimi geliştiriyorum.")
                return "\n".join(lines)
        return None
