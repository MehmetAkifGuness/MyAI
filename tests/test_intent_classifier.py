"""
tests/test_intent_classifier.py
================================
Börü Birleşik Niyet Sınıflandırıcısı (IntentClassifier) Birim Testleri.
"""

import pytest

from boru.nlu.intent_classifier import IntentCategory, IntentClassifier


class TestIntentClassifier:
    """Niyet sınıflandırıcısının CHAT, FEEDBACK, ACTION, CODING kategorilerini doğrulama testleri."""

    @pytest.mark.parametrize(
        "feedback_text",
        [
            "Şarkı çalmadı",
            "Hala açık",
            "kapanmadı",
            "kapatamadın",
            "çalışmadı",
            "açılmadı",
            "yanlış anladın",
            "bunu aramam için söylemedim",
            "bu bir sorun",
            "böyle olsun dememiştim",
        ],
    )
    def test_feedback_intent_detection(self, feedback_text: str):
        res = IntentClassifier.classify(feedback_text)
        assert res.category == IntentCategory.FEEDBACK
        assert res.is_correction is True
        # Geri bildirim veya şikayetlerde asla bağımsız bir uygulama hedefi çıkarılmamalıdır
        assert res.action_type in ("feedback_or_correction", None)

    @pytest.mark.parametrize(
        "chat_text",
        [
            "Selam",
            "Merhaba nasılsın",
            "Bugün nasılsın Börü",
            "Python nedir bana açıklar mısın",
            "Yapay zeka hakkında ne düşünüyorsun",
        ],
    )
    def test_chat_intent_detection(self, chat_text: str):
        res = IntentClassifier.classify(chat_text)
        assert res.category == IntentCategory.CHAT
        assert res.is_correction is False
        assert res.action_type is None

    @pytest.mark.parametrize(
        "action_text, expected_action, expected_target",
        [
            ("Not defterini kapat", "close_app", "Not Defteri"),
            ("Spotify'ı aç", "open_app", "Spotify"),
            ("Chrome'u sonlandır", "close_app", "Chrome"),
            ("Hesap makinesini açar mısın", "open_app", "Hesap Makinesi"),
            ("Ceza'dan Yerli Plaka şarkısını aç", "media_play_target", "Ceza Yerli Plaka"),
            ("ekran görüntüsü al", "take_screenshot", None),
        ],
    )
    def test_action_intent_detection_and_sanitization(
        self, action_text: str, expected_action: str, expected_target: str
    ):
        res = IntentClassifier.classify(action_text)
        assert res.category == IntentCategory.ACTION
        assert res.action_type == expected_action
        if expected_target is not None:
            assert res.sanitized_target == expected_target

    @pytest.mark.parametrize(
        "coding_text",
        [
            "kodla: hızlı sıralama algoritması yaz",
            "refactor: bu fonksiyonu optimize et",
            "def topla(a, b):\n    return a + b",
            "import os\nimport sys",
            "test yaz: bu modül için birim testi ekle",
        ],
    )
    def test_coding_intent_detection(self, coding_text: str):
        res = IntentClassifier.classify(coding_text)
        assert res.category == IntentCategory.CODING

