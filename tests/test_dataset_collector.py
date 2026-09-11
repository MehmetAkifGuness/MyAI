import json
import pytest
from pathlib import Path
from boru.learning.dataset_collector import DatasetCollector


def test_dataset_collector_normal_turn(tmp_path: Path):
    dataset_file = tmp_path / "self_training_dataset.jsonl"
    collector = DatasetCollector(storage_path=dataset_file)

    collector.observe_turn("Python'da hızlı bir API nasıl kurulur?", "FastAPI kullanarak çok hızlı bir API kurabilirsiniz.")
    stats = collector.get_dataset_stats()
    assert stats["total_samples"] == 1
    assert "coding" in stats["categories"]


def test_dataset_collector_sensitive_redaction(tmp_path: Path):
    dataset_file = tmp_path / "self_training_dataset.jsonl"
    collector = DatasetCollector(storage_path=dataset_file)

    collector.observe_turn(
        "API anahtarım sk-123456789012345678901234567890 ve tokenim Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "Anahtarınızı güvenle sakladım."
    )

    with open(dataset_file, "r", encoding="utf-8") as f:
        line = f.readline()
        data = json.loads(line)
        assert "sk-123456789012345678901234567890" not in data["instruction"]
        assert "[REDACTED_API_KEY]" in data["instruction"]


def test_dataset_collector_filter_corrections(tmp_path: Path):
    dataset_file = tmp_path / "self_training_dataset.jsonl"
    collector = DatasetCollector(storage_path=dataset_file)

    collector.observe_turn("yanlış kelimeyi aldın", "Özür dilerim.")
    stats = collector.get_dataset_stats()
    assert stats["total_samples"] == 0
