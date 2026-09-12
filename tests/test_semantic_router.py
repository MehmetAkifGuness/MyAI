"""
Tests for SemanticIntentResolver:
- Flexible spoken Turkish matching
- Informal words, devrik sentences, polite prefixes
- Reminder, media, screen, and organizer resolution
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from boru.tools.semantic_router import SemanticIntentResolver


class TestSemanticIntentResolver:
    def test_resolve_reminder_minutes_and_label(self):
        secs, lbl = SemanticIntentResolver.resolve_reminder("bana kahve molası için 15 dakika sayaç kurar mısın")
        assert secs == 900.0
        assert "Kahve" in lbl

    def test_resolve_reminder_half_hour(self):
        secs, lbl = SemanticIntentResolver.resolve_reminder("yarım saat sonra haber ver lütfen fırına bakacağım")
        assert secs == 1800.0
        assert lbl is not None

    def test_resolve_reminder_seconds(self):
        secs, lbl = SemanticIntentResolver.resolve_reminder("30 saniyelik sayaç başlat sana zahmet")
        assert secs == 30.0

    def test_resolve_reminder_not_a_reminder(self):
        res = SemanticIntentResolver.resolve_reminder("bugün hava durumu nasıl")
        assert res is None

    def test_resolve_media_pause_and_play(self):
        action, _ = SemanticIntentResolver.resolve_media_action("şarkıyı durduruver bir zahmet")
        assert action == "pause"

        action, _ = SemanticIntentResolver.resolve_media_action("müziğe devam ettir lütfen")
        assert action == "play"

    def test_resolve_media_tracks(self):
        action, _ = SemanticIntentResolver.resolve_media_action("sonraki parçaya geç sana zahmet")
        assert action == "next"

        action, _ = SemanticIntentResolver.resolve_media_action("önceki şarkıya dön")
        assert action == "prev"

    def test_resolve_media_play_target(self):
        action, target = SemanticIntentResolver.resolve_media_action("spotifydan Duman açsana")
        assert action == "play_target"
        assert "Duman" in target

    def test_resolve_screen_intent(self):
        intent = SemanticIntentResolver.resolve_screen_intent("bi baksana şu an ekranda ne açık")
        assert intent == "summary"

        intent = SemanticIntentResolver.resolve_screen_intent("ekranda bir hata var mı görsel analiz yap")
        assert intent == "analyze"

        intent = SemanticIntentResolver.resolve_screen_intent("bugün dolar ne kadar")
        assert intent is None

    def test_resolve_organizer_intent(self):
        intent = SemanticIntentResolver.resolve_organizer_intent("masaüstündeki dosyaları toparlamadan önce göster")
        assert intent == "preview"

        intent = SemanticIntentResolver.resolve_organizer_intent("yaptığın masaüstü düzenlemesini geri al lütfen")
        assert intent == "undo"

        intent = SemanticIntentResolver.resolve_organizer_intent("masaüstünü temizle sana zahmet")
        assert intent == "organize"

    def test_resolve_and_execute_dispatches_reminder(self):
        with patch("boru.tools.reminder_tools.ReminderService.schedule", return_value=(1, "Hatırlatıcı kuruldu")):
            res = SemanticIntentResolver.resolve_and_execute("bana 5 dakika sayaç kur")
            assert res is not None
            assert "Hatırlatıcı kuruldu" in res

    def test_resolve_and_execute_dispatches_screen_summary(self):
        mock_agent = MagicMock()
        mock_agent.get_screen_summary.return_value = "Aktif Ekran: Spotify"
        with patch("boru.tools.screen_agent.get_screen_agent", return_value=mock_agent):
            res = SemanticIntentResolver.resolve_and_execute("ekranda ne var bir baksana")
            assert res is not None
            assert "Spotify" in res

