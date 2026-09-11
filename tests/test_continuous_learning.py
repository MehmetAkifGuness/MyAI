import json
import pytest
from pathlib import Path
from boru.learning.continuous_learning import ContinuousLearningEngine
from boru.learning.implicit_memory import ImplicitMemoryLearner


def test_continuous_learning_start_stop_toggle(tmp_path: Path):
    engine = ContinuousLearningEngine(data_dir=tmp_path, interval_seconds=3600)
    assert engine.is_enabled() is True
    assert engine.is_running() is False

    engine.start()
    assert engine.is_running() is True
    engine.stop()
    assert engine.is_running() is False

    msg = engine.toggle_mode(False)
    assert "kapatıldı" in msg
    assert engine.is_enabled() is False

    msg2 = engine.toggle_mode(True)
    assert "açıldı" in msg2
    assert engine.is_enabled() is True


def test_continuous_learning_run_cycle(tmp_path: Path):
    imp_storage = tmp_path / "user_learned_profile.json"
    implicit = ImplicitMemoryLearner(storage_path=imp_storage)
    implicit.observe_turn("Python ve FastAPI ile backend geliştiriyorum.", "Harika!")

    engine = ContinuousLearningEngine(data_dir=tmp_path, implicit_memory=implicit)
    ok = engine.run_cycle()
    assert ok is True

    # Check that knowledge file exists and has entries
    kn_file = tmp_path / "continuous_knowledge.json"
    assert kn_file.exists()
    with open(kn_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) >= 1
        assert "query" in data[0]


def test_continuous_learning_user_understanding(tmp_path: Path):
    engine = ContinuousLearningEngine(data_dir=tmp_path)
    initial_lvl = engine._user_understanding["understanding_level"]

    # Turn 1: Short technical question
    engine.observe_turn("Python'da FastAPI kodla", "İşte FastAPI kodunuz...")
    assert engine._user_understanding["total_turns_observed"] == 1
    assert engine._user_understanding["understanding_level"] >= initial_lvl
    assert "teknik" in engine._user_understanding["communication_style"].lower()
    assert "özlü" in engine._user_understanding["preferred_length"].lower()
    assert "FastAPI" in engine._user_understanding["detected_interests"]

    # Turn 2: Friendly conversational message
    engine.observe_turn("Merhaba Börü nasılsın dostum?", "İyiyim, teşekkürler!")
    assert engine._user_understanding["total_turns_observed"] == 2

    ctx = engine.build_context()
    assert "[Sürekli Öğrenme ve Kullanıcıyı Anlama Modu (Aktif)]" in ctx
    assert "%" in ctx
    assert "Stratejileri" in ctx


def test_continuous_learning_resolve_commands(tmp_path: Path):
    engine = ContinuousLearningEngine(data_dir=tmp_path)
    engine.run_cycle()
    engine.observe_turn("Python yazıyorum", "Anlaşıldı")

    # Status query
    status_res = engine.resolve_command("sürekli öğrenme modu durumu")
    assert status_res is not None
    assert "Börü Sürekli Öğrenme ve Adaptasyon Raporu" in status_res
    assert "AKTİF ÇALIŞIYOR" in status_res

    # Understanding query
    und_res = engine.resolve_command("beni ne kadar anlıyorsun?")
    assert und_res is not None
    assert "Mevcut Anlayış Seviyem" in und_res

    # Strategy query
    strat_res = engine.resolve_command("nasıl cevap vermen gerektiğini öğrendin mi?")
    assert strat_res is not None
    assert "yanıt verme kuralları" in strat_res

    # Research query
    res_query = engine.resolve_command("internetten ne araştırdın?")
    assert res_query is not None
    assert "otonom araştırma" in res_query.lower()


def test_system_tools_integration_continuous_learning(tmp_path: Path, monkeypatch):
    import boru.learning as bl
    engine = ContinuousLearningEngine(data_dir=tmp_path)
    monkeypatch.setattr(bl, "_GLOBAL_CONTINUOUS_LEARNING_ENGINE", engine)

    from boru.tools.system_tools import resolve_system_command
    ans = resolve_system_command("sürekli öğrenme modu")
    assert ans is not None
    assert "Börü Sürekli Öğrenme" in ans

    ans2 = resolve_system_command("beni ne kadar anlıyorsun")
    assert ans2 is not None
    assert "Mevcut Anlayış Seviyem" in ans2
