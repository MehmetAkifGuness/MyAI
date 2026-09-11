import pytest
from pathlib import Path
from boru.learning.self_reflection import SelfReflectionLearner


def test_self_reflection_conversation_correction(tmp_path: Path):
    storage = tmp_path / "reflection_rules.json"
    learner = SelfReflectionLearner(storage_path=storage)

    # Turn 1: Mistaken action trigger
    learner.observe_turn("bakacağız", "Bakmak ne yapacaksın?")

    # Turn 2: User corrects the assistant
    learner.observe_turn("Seninle konuştuğumuz için gitti yanlış kelimeyi aldı", "Anladım, sohbet ediyoruz.")

    rules = learner.get_rules()
    assert len(rules) >= 1
    rule = rules[0]
    assert "bakacağız" in rule["lesson"] or rule["rule_type"] == "intent_overtrigger"

    # Context generation
    ctx = learner.build_context()
    assert "[Öğrenilmiş Düzeltmeler ve Hata Önleme Kuralları]" in ctx
    assert "bakacağız" in ctx


def test_self_reflection_weather_disambiguation(tmp_path: Path):
    storage = tmp_path / "reflection_rules.json"
    learner = SelfReflectionLearner(storage_path=storage)

    # Turn 1: Weather confusion with "anki"
    learner.observe_turn("Kahramanmaraş için şu anki hava durumunu söyle", "Anki için hava durumu: Açık +23°C.")

    # Turn 2: User points out the error
    learner.observe_turn("yani havanın 23 derece olduğunda mı bahsettim, yanlış anladın", "Özür dilerim.")

    rules = learner.get_rules()
    assert len(rules) >= 1
    assert any(r["rule_type"] == "entity_disambiguation" for r in rules)


def test_self_reflection_resolve_query(tmp_path: Path):
    storage = tmp_path / "reflection_rules.json"
    learner = SelfReflectionLearner(storage_path=storage)

    learner.observe_turn("aç", "Açmak ne istiyorsun?")
    learner.observe_turn("öyle demedim, yanlış kelimeyi aldın", "Affedersiniz.")

    ans = learner.resolve_rules_query("hatalarından ne öğrendin?")
    assert ans is not None
    assert "dersler" in ans
