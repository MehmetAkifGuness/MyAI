"""
boru.nlu.intent_router
======================
Kullanıcının serbest doğal dil ifadelerini ('kodla:', 'iyileştir:' gibi
ön ekler olmadan) anlamsal olarak analiz edip ilgili alt koordinatörün
beklediği formata otomatik dönüştüren akıllı niyet yönlendiricisi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RoutedIntent(str, Enum):
    CODING = "CODING"
    IMPROVEMENT = "IMPROVEMENT"
    TESTING = "TESTING"
    TEST_GENERATION = "TEST_GENERATION"
    RESEARCH = "RESEARCH"
    STATUS = "STATUS"
    GENERAL_CHAT = "GENERAL_CHAT"


@dataclass(frozen=True, slots=True)
class IntentRouteResult:
    intent: RoutedIntent
    confidence: float
    transformed_message: str
    original_message: str


class FreeFormIntentRouter:
    """
    Kullanıcının girdiği serbest Türkçe ifadeleri regex + morfolojik niyet
    analiziyle uygun araç formatına ('kodla: ...', 'iyileştir: ...') dönüştürür.
    """

    # Dosya uzantısı tespiti
    _FILE_REGEX = re.compile(
        r"\b(?P<path>[a-zA-Z0-9_\-\./\\]+\.(?:py|json|md|txt|html|css|js|sql|yaml|yml|toml))\b",
        re.IGNORECASE,
    )

    # Test üretme niyetleri
    _TEST_GENERATE_PATTERNS = (
        re.compile(r"\b(?:test\s+üret|test\s+uret|test\s+oluştur|test\s+olustur|testlerini\s+yaz|testlerini\s+oluştur|test\s+yaz)\b", re.IGNORECASE),
    )

    # Kodlama / Ekleme / Fonksiyon yazma niyetleri
    _CODING_PATTERNS = (
        re.compile(r"\b(?:kodla|kodunu\s+yaz|kodu\s+yaz|fonksiyon\s+yaz|fonksiyonu\s+ekle|yeni\s+fonksiyon|class\s+ekle|sınıf\s+ekle)\b", re.IGNORECASE),
        re.compile(r"\b(?:içine|içerisine|dosyasına|dosyaya)\s+(?:ekle|yaz|oluştur|tanımla)\b", re.IGNORECASE),
        re.compile(r"\b(?:bir\s+özellik|özelliği|metot|metodu)\s+(?:ekle|yaz)\b", re.IGNORECASE),
    )

    # İyileştirme / Refactor / Hata düzeltme niyetleri
    _IMPROVEMENT_PATTERNS = (
        re.compile(r"\b(?:iyileştir|refactor\s+et|düzenle|düzelt|hatayı\s+çöz|hatayı\s+gider|bug\s+fix|optimize\s+et)\b", re.IGNORECASE),
        re.compile(r"\b(?:temizle|güncelle|değiştir)\b", re.IGNORECASE),
    )

    # Test çalıştırma niyetleri
    _TEST_PATTERNS = (
        re.compile(r"\b(?:test\s+et|testleri\s+çalıştır|testleri\s+koş|test\s+ajanı)\b", re.IGNORECASE),
    )

    # Durum / Kendini değerlendirme niyetleri
    _STATUS_PATTERNS = (
        re.compile(r"\b(?:kendini\s+değerlendir|durum\s+raporu|web\s+durum|hafıza\s+durumu|sistem\s+durumu)\b", re.IGNORECASE),
    )

    def route(self, user_message: str) -> IntentRouteResult:
        raw = user_message.strip()
        if not raw:
            return IntentRouteResult(
                intent=RoutedIntent.GENERAL_CHAT,
                confidence=1.0,
                transformed_message=raw,
                original_message=raw,
            )

        # Zaten açık bir komut ön eki varsa dokunma (örn: 'kodla:', 'iyileştir:', 'yardım', 'test üret:')
        colon_prefix = raw.partition(":")[0].strip().casefold()
        if colon_prefix in {"kodla", "coding", "iyileştir", "iyilestir", "test ajanı", "test üret", "test uret", "test oluştur", "test yaz", "araştır", "web araştır"}:
            intent = RoutedIntent.TEST_GENERATION if "üret" in colon_prefix or "yaz" in colon_prefix and "test" in colon_prefix else (RoutedIntent.CODING if "kod" in colon_prefix else RoutedIntent.IMPROVEMENT)
            return IntentRouteResult(
                intent=intent,
                confidence=1.0,
                transformed_message=raw,
                original_message=raw,
            )

        file_matches = self._FILE_REGEX.findall(raw)

        # 1. Test Üretme niyeti kontrolü (Örn: 'boru/tools.py için test üret/yaz')
        for pattern in self._TEST_GENERATE_PATTERNS:
            if pattern.search(raw):
                if file_matches:
                    transformed = f"test üret: {file_matches[0]}"
                    return IntentRouteResult(
                        intent=RoutedIntent.TEST_GENERATION,
                        confidence=0.92,
                        transformed_message=transformed,
                        original_message=raw,
                    )

        # 2. Test Çalıştırma niyeti kontrolü
        for pattern in self._TEST_PATTERNS:
            if pattern.search(raw):
                if file_matches:
                    transformed = f"test ajanı: {', '.join(file_matches)}"
                    return IntentRouteResult(
                        intent=RoutedIntent.TESTING,
                        confidence=0.9,
                        transformed_message=transformed,
                        original_message=raw,
                    )

        # 2. İyileştirme niyeti kontrolü (Belirli bir dosya + düzelt/iyileştir)
        for pattern in self._IMPROVEMENT_PATTERNS:
            if pattern.search(raw):
                if file_matches:
                    # 'iyileştir: dosya.py | hedef' formatı
                    paths_str = ", ".join(file_matches)
                    transformed = f"iyileştir: {paths_str} | {raw}"
                    return IntentRouteResult(
                        intent=RoutedIntent.IMPROVEMENT,
                        confidence=0.88,
                        transformed_message=transformed,
                        original_message=raw,
                    )

        # 3. Kodlama niyeti kontrolü
        for pattern in self._CODING_PATTERNS:
            if pattern.search(raw):
                transformed = f"kodla: {raw}"
                return IntentRouteResult(
                    intent=RoutedIntent.CODING,
                    confidence=0.85,
                    transformed_message=transformed,
                    original_message=raw,
                )

        # 4. Durum kontrolü
        for pattern in self._STATUS_PATTERNS:
            if pattern.search(raw):
                return IntentRouteResult(
                    intent=RoutedIntent.STATUS,
                    confidence=0.95,
                    transformed_message=raw,
                    original_message=raw,
                )

        # 5. Varsayılan: Genel Sohbet
        return IntentRouteResult(
            intent=RoutedIntent.GENERAL_CHAT,
            confidence=0.7,
            transformed_message=raw,
            original_message=raw,
        )

