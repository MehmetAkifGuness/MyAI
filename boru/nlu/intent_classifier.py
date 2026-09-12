"""
boru.nlu.intent_classifier
===========================
Börü için Birleşik Niyet Süzgeci ve Sınıflandırıcı (Unified Intent Classifier).

Kullanıcıdan gelen sesli ve yazılı girdileri araçlara veya arama motorlarına
doğrudan iletmeden önce kesin niyet ayrımına tabi tutar:
- CHAT: Sohbet, selamlaşma, felsefe, genel sorular (Araç tetiklenmez).
- FEEDBACK: Eleştiri, hata bildirimi, itiraz, "Hala açık" gibi düzeltmeler (Araç tetiklenmez, self-correction'a yönlendirilir).
- ACTION: İşletim sistemi, medya, uygulama yönetimi (Dolgu kelimeleri temizlenip saf parametre çıkarılır).
- CODING: Kodlama, refactoring, test çalıştırma.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from boru.tools.semantic_router import SemanticIntentResolver

logger = logging.getLogger(__name__)


class IntentCategory(str, Enum):
    FEEDBACK = "FEEDBACK"
    CHAT = "CHAT"
    ACTION = "ACTION"
    CODING = "CODING"


@dataclass(frozen=True, slots=True)
class IntentClassificationResult:
    category: IntentCategory
    action_type: Optional[str]
    sanitized_target: Optional[str]
    is_correction: bool
    confidence: float
    raw_text: str
    explanation: Optional[str] = None


class IntentClassifier:
    """
    Kullanıcı girdisini analiz eden ve kesin niyet kategorisini belirleyen sınıflandırıcı.
    """

    # Açık kodlama anahtar kelimeleri ve kalıpları
    _CODING_PATTERNS = [
        re.compile(r"^(?:kodla|refactor|test\s+et|test\s+yaz|iyileştir|optimize\s+et)\s*:", re.IGNORECASE),
        re.compile(r"```[\s\S]*?```"),
        re.compile(r"\b(?:def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+\s+import)\b"),
        re.compile(r"\b(?:kodunu\s+yaz|fonksiyonu\s+yaz|unit\s+testini\s+yaz|kodla\s+bunu)\b", re.IGNORECASE),
    ]

    # Düzeltme & İtiraz anahtar kelimeleri ("Hala açık", "Kapanmadı", "Çalışmadı" vb.)
    _CORRECTION_PATTERNS = [
        re.compile(r"\b(?:hala\s+(?:açık|çalışıyor|kapanmadı|duruyor|gitmedi|kapanmamış))\b", re.IGNORECASE),
        re.compile(r"\b(?:kapanmadı|kapanmamış|kapatamadın|kapatmadın)\b", re.IGNORECASE),
        re.compile(r"\b(?:açılmadı|açılmamış|açamadın|açmadın)\b", re.IGNORECASE),
        re.compile(r"\b(?:çalmadı|çalmıyor|çalamadın|çalmadın)\b", re.IGNORECASE),
        re.compile(r"\b(?:çalışmadı|çalışmıyor|başlamadı|olmadı|yapamadın|beceremedin)\b", re.IGNORECASE),
        re.compile(r"\b(?:yanlış\s+(?:anladın|yaptın|açtın|çaldın|kapattın|şeyi))\b", re.IGNORECASE),
        re.compile(r"\b(?:bunu\s+(?:aramam|araman|açman|çalman)\s+için\s+(?:söylemedim|demedim))\b", re.IGNORECASE),
        re.compile(r"\b(?:arama\s+(?:yap\s+demedim|yapma|yapmanı\s+istemedim))\b", re.IGNORECASE),
        re.compile(r"\b(?:bu\s+bir\s+(?:sorun|hata|problem))\b", re.IGNORECASE),
        re.compile(r"\b(?:böyle\s+olsun\s+dememiştim)\b", re.IGNORECASE),
    ]

    # Uygulama Kapatma Kalıpları
    _CLOSE_PATTERNS = [
        re.compile(r"^(?:lütfen\s+)?(?:şu\s+)?(.+?)\s+(?:kapat|sonlandır|durdur|öldür|çık|kapatıver|kapatır\s+mısın)$", re.IGNORECASE),
        re.compile(r"^(?:kapat|sonlandır|durdur)\s+(?:lütfen\s+)?(?:şu\s+)?(.+)$", re.IGNORECASE),
    ]

    # Uygulama Açma Kalıpları
    _OPEN_PATTERNS = [
        re.compile(r"^(?:lütfen\s+)?(?:şu\s+)?(.+?)\s+(?:aç|başlat|çalıştır|açıver|açar\s+mısın|açabilir\s+misin)$", re.IGNORECASE),
        re.compile(r"^(?:aç|başlat|çalıştır)\s+(?:lütfen\s+)?(?:şu\s+)?(.+)$", re.IGNORECASE),
    ]

    # Medya ve Müzik Kalıpları
    _MEDIA_PATTERNS = [
        re.compile(r"\b(?:şarkı|müzik|parça|klip|video|çal|dinlet)\b", re.IGNORECASE),
    ]

    @classmethod
    def classify(cls, text: str) -> IntentClassificationResult:
        raw = text.strip()
        if not raw:
            return IntentClassificationResult(
                category=IntentCategory.CHAT,
                action_type=None,
                sanitized_target=None,
                is_correction=False,
                confidence=1.0,
                raw_text=raw,
                explanation="Boş girdi genel sohbet kabul edildi.",
            )

        cleaned = raw.lower().strip(".!?,:;")

        # ── 1. ÖNCELİK: Hata Bildirimi, Eleştiri ve Düzeltmeler (FEEDBACK) ────────
        # "Hala açık", "Kapanmadı", "Şarkı çalmadı", "Bunu araman için söylemedim"
        is_correction = any(p.search(cleaned) for p in cls._CORRECTION_PATTERNS)
        feedback_direct = SemanticIntentResolver.resolve_feedback_intent(raw)

        if is_correction or feedback_direct is not None:
            return IntentClassificationResult(
                category=IntentCategory.FEEDBACK,
                action_type="feedback_or_correction",
                sanitized_target=None,
                is_correction=True,
                confidence=0.98,
                raw_text=raw,
                explanation="Kullanıcı bir hata, itiraz veya düzeltme bildirdi; araç tetiklenmemelidir.",
            )

        # ── 2. ÖNCELİK: Kodlama ve Geliştirme (CODING) ───────────────────────────
        for p in cls._CODING_PATTERNS:
            if p.search(raw):
                return IntentClassificationResult(
                    category=IntentCategory.CODING,
                    action_type="code_task",
                    sanitized_target=None,
                    is_correction=False,
                    confidence=0.95,
                    raw_text=raw,
                    explanation="Kodlama veya test görevi tespit edildi.",
                )

        # ── 3. ÖNCELİK: İşletim Sistemi Otomasyon Komutları (ACTION) ────────────
        # A. Kapatma Eylemleri
        for pat in cls._CLOSE_PATTERNS:
            m = pat.match(cleaned)
            if m:
                target = m.group(1).strip()
                # "kapat" kelimesinin kendisi veya boş hedef değilse
                if target and target not in ("kapat", "sonlandır", "durdur", "uygulamayı", "programı"):
                    clean_target = cls._sanitize_action_target(target)
                    return IntentClassificationResult(
                        category=IntentCategory.ACTION,
                        action_type="close_app",
                        sanitized_target=clean_target,
                        is_correction=False,
                        confidence=0.95,
                        raw_text=raw,
                        explanation=f"Uygulama kapatma eylemi: {clean_target}",
                    )

        # B. Medya / Müzik Eylemleri
        media_res = SemanticIntentResolver.resolve_media_action(raw)
        if media_res is not None:
            action, target = media_res
            return IntentClassificationResult(
                category=IntentCategory.ACTION,
                action_type=f"media_{action}",
                sanitized_target=target,
                is_correction=False,
                confidence=0.95,
                raw_text=raw,
                explanation=f"Medya eylemi: {action} ({target})",
            )

        # C. Uygulama Açma Eylemleri
        for pat in cls._OPEN_PATTERNS:
            m = pat.match(cleaned)
            if m:
                target = m.group(1).strip()
                if target and target not in ("aç", "başlat", "çalıştır", "uygulamayı", "programı", "bunu", "şunu"):
                    clean_target = cls._sanitize_action_target(target)
                    return IntentClassificationResult(
                        category=IntentCategory.ACTION,
                        action_type="open_app",
                        sanitized_target=clean_target,
                        is_correction=False,
                        confidence=0.92,
                        raw_text=raw,
                        explanation=f"Uygulama açma eylemi: {clean_target}",
                    )

        # D. Ekran ve Ses Komutları
        if any(k in cleaned for k in ("ekran görüntüsü", "ekran resmi", "screenshot")):
            return IntentClassificationResult(
                category=IntentCategory.ACTION,
                action_type="take_screenshot",
                sanitized_target=None,
                is_correction=False,
                confidence=0.95,
                raw_text=raw,
                explanation="Ekran görüntüsü alma eylemi",
            )

        if any(k in cleaned for k in ("sesi aç", "sesi kıs", "sesi yükselt", "sesi azalt", "sessize al")):
            return IntentClassificationResult(
                category=IntentCategory.ACTION,
                action_type="system_volume",
                sanitized_target=cleaned,
                is_correction=False,
                confidence=0.95,
                raw_text=raw,
                explanation="Sistem ses seviyesi kontrolü",
            )

        # ── 4. VARSAYILAN: Genel Sohbet ve Bilgi Talebi (CHAT) ───────────────────
        return IntentClassificationResult(
            category=IntentCategory.CHAT,
            action_type=None,
            sanitized_target=None,
            is_correction=False,
            confidence=0.90,
            raw_text=raw,
            explanation="Genel sohbet, soru-cevap veya bilgi talebi.",
        )

    @staticmethod
    def _sanitize_action_target(text: str) -> str:
        """Hedef uygulama veya komuttaki Türkçe iyelik/ayrılma eklerini temizler."""
        cand = text.strip()
        # Dolguları temizle
        cand = re.sub(r"\b(?:lütfen|şu|bir|bize|bana|hemen|hızlıca)\b", "", cand, flags=re.IGNORECASE).strip()

        # Bilinen uygulama adları kontrolü
        from boru.tools.closed_loop import APP_NAME_TO_EXE
        low = cand.lower().strip()
        for known in APP_NAME_TO_EXE:
            if low == known:
                return known.title()
            if low.startswith(known) and (len(low) - len(known)) <= 4:
                return known.title()

        # Kesme işaretli ekler: chrome'u -> chrome, spotify'ı -> spotify
        cand = re.sub(r"'(?:[ıiuüae]|y[ıiuüae]|n[ıiuüae])?$", "", cand, flags=re.IGNORECASE)
        # Sondaki belirtme ekleri: defterini -> defteri, makinesini -> makinesi
        cand = re.sub(r"(?<=[a-zA-ZçÇğĞıİöÖşŞüÜ])(?:ni|nı|nu|nü)$", "", cand, flags=re.IGNORECASE)
        cand = re.sub(r"(?<=[a-zA-ZçÇğĞıİöÖşŞüÜ])(?:yi|yı|yu|yü)$", "", cand, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cand).strip().title()
