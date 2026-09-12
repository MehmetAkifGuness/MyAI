"""
tests/test_feedback_intent_separation.py
=========================================
Börü'nün Niyet Ayrımı (Intent Separation), Eleştiri/Hata Bildirimi Yönetimi
ve Saf Medya/Arama Parametresi Temizliği Birim Testleri.
"""

from unittest.mock import MagicMock, patch
import pytest

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.learning.self_reflection import SelfReflectionLearner
from boru.prompts import SystemPromptFactory
from boru.tools.semantic_router import SemanticIntentResolver
from boru.tools.system_tools import resolve_system_command
from boru.tools.web_search import resolve_web_search_command


class TestFeedbackIntentSeparation:
    """Eleştiri ve hata bildirimlerinin komutlardan ayrılması testleri."""

    @pytest.mark.parametrize(
        "feedback_phrase",
        [
            "Şarkı çalmadı",
            "şarkı çalmıyor",
            "müzik çalmadı ki",
            "çalışmadı",
            "açılmadı",
            "ses gelmiyor",
            "ses çıkmıyor",
            "Yanlış anladın",
            "yanlış şey açtın",
            "bunu aramam için söylemedim",
            "bunu araman için söylemedim",
            "bunu sana araman için söylemedim",
            "arama yap demedim",
            "arama yapmanı istemedim",
            "böyle olsun dememiştim",
            "bu bir sorun",
            "hatalısın",
            "öyle demedim",
            "bunu kastetmedim",
        ],
    )
    def test_feedback_phrases_detected_and_politely_handled(self, feedback_phrase: str):
        """Eleştiri ve hata ifadeleri asla None dönmemeli, kibar geri bildirim üretmeli."""
        response = SemanticIntentResolver.resolve_feedback_intent(feedback_phrase)
        assert response is not None
        assert any(
            kw in response.lower()
            for kw in ("kusura bakmayın", "teşekkür", "farkındayım", "not aldım", "kaydettim", "anladım")
        )

    @pytest.mark.parametrize(
        "complaint",
        [
            "şarkı çalmadı",
            "şarkı çalmıyor",
            "çalamadın",
            "müzik açılmadı",
        ],
    )
    def test_complaints_do_not_trigger_media_actions(self, complaint: str):
        """Şikayet cümleleri asla 'Madı' vb. müzik oynatma hedefi üretmemeli."""
        media_action = SemanticIntentResolver.resolve_media_action(complaint)
        assert media_action is None

    @pytest.mark.parametrize(
        "search_complaint",
        [
            "bunu aramam için söylemedim",
            "bunu araman için söylemedim",
            "arama yap demedim",
            "arama yapmanı istemedim",
        ],
    )
    def test_complaints_do_not_trigger_web_searches(self, search_complaint: str):
        """Arama şikayetleri asla DuckDuckGo/Google araması yapmamalı, geri bildirim dönmeli."""
        with patch("boru.tools.web_search.search_web_live") as mock_web_search:
            res = resolve_web_search_command(search_complaint)
            mock_web_search.assert_not_called()
            assert res is not None
            assert "arama" in res.lower() or "kusura bakmayın" in res.lower()

    def test_system_command_resolver_intercepts_feedback(self):
        """resolve_system_command eleştiri veya hata bildiriminde işletim sistemi komutu çalıştırmaz."""
        res = resolve_system_command("Şarkı çalmadı")
        assert res is not None
        assert "kusura bakmayın" in res.lower()

    def test_system_command_resolver_intercepts_unwanted_search(self):
        """resolve_system_command 'bunu araman için söylemedim' dendiğinde arama motoru açmaz."""
        with patch("boru.tools.system_tools.search_web") as mock_search:
            res = resolve_system_command("Bunu araman için söylemedim")
            mock_search.assert_not_called()
            assert res is not None
            assert "kusura bakmayın" in res.lower() or "arama" in res.lower()


class TestMediaParamSanitization:
    """Müzik ve medya sorgularından eklerin ve dolguların temizlenmesi testleri."""

    def test_sanitize_artist_and_song_suffixes(self):
        """Ceza'dan Yerli Plaka şarkısını aç -> Ceza Yerli Plaka"""
        cleaned = SemanticIntentResolver.sanitize_media_query("Ceza'dan Yerli Plaka şarkısını aç")
        assert cleaned == "Ceza Yerli Plaka"

    def test_sanitize_platform_and_video(self):
        """Spotify'dan Duman klibini aç -> Duman"""
        cleaned = SemanticIntentResolver.sanitize_media_query("Spotify'dan Duman klibini aç")
        assert cleaned == "Duman"

    def test_sanitize_politeness_and_fillers(self):
        """Bize bir Sezen Aksu çalsana lütfen -> Sezen Aksu"""
        cleaned = SemanticIntentResolver.sanitize_media_query("Bize bir Sezen Aksu çalsana lütfen")
        assert cleaned == "Sezen Aksu"

    def test_sanitize_complex_query(self):
        """Ezhel'den Geceler parçasını çalabilir misin -> Ezhel Geceler"""
        cleaned = SemanticIntentResolver.sanitize_media_query("Ezhel'den Geceler parçasını çalabilir misin")
        assert cleaned == "Ezhel Geceler"

    def test_resolve_media_action_with_pure_target(self):
        """Ceza'dan Sus Pus çal -> ('play_target', 'Ceza Sus Pus')"""
        res = SemanticIntentResolver.resolve_media_action("Ceza'dan Sus Pus şarkısını aç")
        assert res is not None
        action, target = res
        assert action == "play_target"
        assert target == "Ceza Sus Pus"


class TestAssistantEndToEndFeedbackInterception:
    """Asistan katmanında niyet ayrımının uçtan uca doğrulanması."""

    def test_assistant_intercepts_feedback_before_llm(self):
        """Kullanıcı 'Şarkı çalmadı' dediğinde LLM çağrılmadan doğrudan kibar özür dönmeli."""
        mock_model = MagicMock()
        history = ConversationHistory()
        prompt_factory = SystemPromptFactory("Börü", conversational=True)

        assistant = AssistantService(
            chat_model=mock_model,
            conversation_history=history,
            prompt_factory=prompt_factory,
        )

        response = assistant.reply("Şarkı çalmadı")
        # LLM'e gitmeden doğrudan çözülmeli
        mock_model.generate_response.assert_not_called()
        assert "kusura bakmayın" in response.lower()

    def test_assistant_intercepts_wrong_search_feedback(self):
        """Kullanıcı 'Bunu araman için söylemedim' dediğinde LLM çağrılmadan kibar yanıt dönmeli."""
        mock_model = MagicMock()
        history = ConversationHistory()
        prompt_factory = SystemPromptFactory("Börü", conversational=True)

        assistant = AssistantService(
            chat_model=mock_model,
            conversation_history=history,
            prompt_factory=prompt_factory,
        )

        response = assistant.reply("Bunu araman için söylemedim")
        mock_model.generate_response.assert_not_called()
        assert "kusura bakmayın" in response.lower() or "arama" in response.lower()


class TestSelfReflectionLearningOnFeedback:
    """Hata ve eleştiri bildirimlerinin Börü'nün öğrenme motoruna aktarılması."""

    def test_reflection_learns_from_complaint(self, tmp_path):
        rules_file = tmp_path / "reflection_rules.json"
        learner = SelfReflectionLearner(storage_path=rules_file)

        # 1. Tur: Asistan müzik açmaya çalıştı ama olmadı
        learner.observe_turn("Ceza aç", "Spotify'da Ceza açılıyor.")

        # 2. Tur: Kullanıcı hata bildirdi
        learner.observe_turn("Şarkı çalmadı", "Kusura bakmayın, işlem gerçekleşmemiş görünüyor.")

        rules = learner.get_rules()
        assert len(rules) >= 1
        lesson_text = rules[0].get("lesson", "")
        assert "Kullanıcı eleştiri, şikayet veya hata bildirdiğinde" in lesson_text
        assert "asla bir arama veya komut olarak yürütme" in lesson_text
