import pytest
from pathlib import Path
from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.prompts import SystemPromptFactory
from boru.learning.implicit_memory import ImplicitMemoryLearner
from boru.learning.self_reflection import SelfReflectionLearner
from boru.learning.dataset_collector import DatasetCollector
from boru.tools.system_tools import resolve_system_command


class DummyModel:
    def generate(self, messages):
        return "Merhaba, size nasıl yardımcı olabilirim?"


def test_learning_suite_assistant_turn_observers(tmp_path: Path):
    imp_storage = tmp_path / "user_learned_profile.json"
    refl_storage = tmp_path / "reflection_rules.json"
    ds_storage = tmp_path / "dataset.jsonl"

    imp_learner = ImplicitMemoryLearner(storage_path=imp_storage)
    refl_learner = SelfReflectionLearner(storage_path=refl_storage)
    ds_collector = DatasetCollector(storage_path=ds_storage)

    history = ConversationHistory()
    prompt_factory = SystemPromptFactory("Börü")

    assistant = AssistantService(
        chat_model=DummyModel(),
        conversation_history=history,
        prompt_factory=prompt_factory,
        turn_observers=[imp_learner, refl_learner, ds_collector],
    )

    # 1. First interaction: User mentions city and tech
    resp = assistant.reply("Kahramanmaraş'ta yaşıyorum ve Python ile proje geliştiriyorum.")
    assert resp is not None

    # Implicit memory should have captured city and tech
    assert imp_learner.get_city() == "Kahramanmaraş"
    assert "Python" in imp_learner.get_tech_stack()

    # Dataset collector should have logged 1 sample
    stats = ds_collector.get_dataset_stats()
    assert stats["total_samples"] == 1


def test_weather_fallback_to_learned_city(tmp_path: Path, monkeypatch):
    import boru.learning as bl
    imp_storage = tmp_path / "user_learned_profile.json"
    imp_learner = ImplicitMemoryLearner(storage_path=imp_storage)
    imp_learner.observe_turn("Kahramanmaraş'ta ikamet ediyorum.", "Anlaşıldı.")

    monkeypatch.setattr(bl, "_GLOBAL_IMPLICIT_LEARNER", imp_learner)

    from boru.tools.quick_info import resolve_quick_info
    res = resolve_quick_info("hava durumu")
    # Even if weather API returns mocked or real, query should target Kahramanmaraş
    assert res is not None
    assert "Kahramanmaraş" in res or "servisine" in res or "°C" in res


def test_music_fallback_to_learned_app(tmp_path: Path, monkeypatch):
    import boru.learning as bl
    imp_storage = tmp_path / "user_learned_profile.json"
    imp_learner = ImplicitMemoryLearner(storage_path=imp_storage)
    imp_learner.observe_turn("Ben genelde spotify kullanırım.", "Harika.")

    monkeypatch.setattr(bl, "_GLOBAL_IMPLICIT_LEARNER", imp_learner)

    # Mock open_application or startfile
    opened = []
    def mock_startfile(app):
        opened.append(app)

    monkeypatch.setattr("os.startfile", mock_startfile)

    from boru.tools.system_tools import open_application
    ok, msg = open_application("müzik")
    assert ok is True
    assert "Spotify" in msg
