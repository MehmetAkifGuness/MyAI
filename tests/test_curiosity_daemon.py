import pytest
from pathlib import Path
from boru.learning.implicit_memory import ImplicitMemoryLearner
from boru.learning.curiosity_daemon import CuriosityDaemon


def test_curiosity_run_cycle(tmp_path: Path):
    storage = tmp_path / "curiosity_knowledge.json"
    mem_storage = tmp_path / "user_learned_profile.json"

    implicit = ImplicitMemoryLearner(storage_path=mem_storage)
    implicit.observe_turn("Kahramanmaraş'ta Python ve FastAPI yazıyorum.", "Süper!")

    daemon = CuriosityDaemon(storage_path=storage, implicit_memory=implicit)
    ok = daemon.run_cycle()
    assert ok is True

    insights = daemon.get_latest_insights()
    assert len(insights) >= 2

    # Check query response
    resp = daemon.resolve_curiosity_query("bugün ne öğrendin?")
    assert resp is not None
    assert "otonom gözlem" in resp


def test_curiosity_start_stop(tmp_path: Path):
    storage = tmp_path / "curiosity_knowledge.json"
    daemon = CuriosityDaemon(storage_path=storage, interval_seconds=3600)

    daemon.start()
    assert daemon._thread is not None
    assert daemon._thread.is_alive()

    daemon.stop()
    assert daemon._thread is None
