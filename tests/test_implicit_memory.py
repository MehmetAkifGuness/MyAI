import json
import pytest
from pathlib import Path
from boru.learning.implicit_memory import ImplicitMemoryLearner


def test_implicit_city_extraction_explicit(tmp_path: Path):
    storage = tmp_path / "user_learned_profile.json"
    learner = ImplicitMemoryLearner(storage_path=storage)

    assert learner.get_city() is None

    learner.observe_turn("Ben Kahramanmaraş'ta yaşıyorum, buranın havası çok güzel.", "Harika!")
    assert learner.get_city() == "Kahramanmaraş"

    # Reload from disk
    new_learner = ImplicitMemoryLearner(storage_path=storage)
    assert new_learner.get_city() == "Kahramanmaraş"


def test_implicit_city_from_weather_query(tmp_path: Path):
    storage = tmp_path / "user_learned_profile.json"
    learner = ImplicitMemoryLearner(storage_path=storage)

    learner.observe_turn("Kahramanmaraş için hava durumu nasıl?", "Hava açık +24°C.")
    assert learner.get_city() == "Kahramanmaraş"


def test_implicit_tech_stack_extraction(tmp_path: Path):
    storage = tmp_path / "user_learned_profile.json"
    learner = ImplicitMemoryLearner(storage_path=storage)

    learner.observe_turn("Python ve FastAPI ile yeni bir mikroservis projesi yazıyorum.", "Başarılar!")
    techs = learner.get_tech_stack()
    assert "Python" in techs
    assert "FastAPI" in techs


def test_implicit_app_preferences(tmp_path: Path):
    storage = tmp_path / "user_learned_profile.json"
    learner = ImplicitMemoryLearner(storage_path=storage)

    learner.observe_turn("Bana Spotify'dan biraz müzik açar mısın?", "Spotify açıldı.")
    assert learner.get_app_preference("music") == "spotify"

    learner.observe_turn("Chrome üzerinden tarayıcıda ara", "Chrome açıldı.")
    assert learner.get_app_preference("browser") == "chrome"


def test_implicit_personal_facts_and_context(tmp_path: Path):
    storage = tmp_path / "user_learned_profile.json"
    learner = ImplicitMemoryLearner(storage_path=storage)

    learner.observe_turn("Ben bir yazılımcıyım ve geceleri kod yazıyorum.", "Kolay gelsin.")
    ctx = learner.build_context()
    assert "Yazılımcı / Geliştirici" in ctx

    # Now add city and tech and check context output
    learner.observe_turn("Kahramanmaraş'tayım ve Python kullanıyorum.", "Anlaşıldı.")
    ctx2 = learner.build_context()
    assert "Kahramanmaraş" in ctx2
    assert "Python" in ctx2
