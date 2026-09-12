"""
Tests for system robustness improvements:
- Local isolated sandbox executor & hybrid fallback
- Persistent reminder service
- Atomic notes service with backup recovery
- Desktop organizer preview and undo journal
- Resilient web search with Wikipedia fallback
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from boru.sandbox.executor import (
    HybridSandboxExecutor,
    LocalIsolatedSandboxExecutor,
)
from boru.tools.command_models import (
    CommandExecutionResult,
    CommandKind,
    CommandRequest,
    CommandRisk,
    CommandSpec,
)
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.reminder_tools import ReminderService
from boru.tools.notes_tools import NotesService
from boru.tools.file_organizer import organize_desktop, undo_organize_desktop
from boru.tools.web_search import search_web_live, _SEARCH_CACHE


class TestLocalIsolatedSandbox:
    def test_status(self, tmp_path):
        executor = LocalIsolatedSandboxExecutor(root=tmp_path)
        status = executor.status()
        assert "Durum: HAZIR" in status
        assert "Yerel İzolasyon" in status

    def test_execute_canonical_command(self, tmp_path):
        # Create minimal repo structure
        (tmp_path / "sample.py").write_text("X = 1\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_sample.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_x(self): pass\n",
            encoding="utf-8",
        )

        executor = LocalIsolatedSandboxExecutor(root=tmp_path, timeout_seconds=15)
        spec = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, ""))

        result = executor.execute(spec)
        assert isinstance(result, CommandExecutionResult)
        assert result.exit_code == 0

    def test_disallowed_command_raises_value_error(self, tmp_path):
        executor = LocalIsolatedSandboxExecutor(root=tmp_path)
        spec = CommandSpec(
            kind=CommandKind.ENVIRONMENT,
            executable="malicious_binary",
            arguments=("bad", "arg"),
            display="Disallowed command",
            risk=CommandRisk.BLOCKED,
        )
        with pytest.raises(ValueError, match="Sandbox yalnızca izinli"):
            executor.execute(spec)

    def test_hybrid_fallback_when_docker_offline(self, tmp_path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_dummy.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_1(self): pass\n",
            encoding="utf-8",
        )

        hybrid = HybridSandboxExecutor(root=tmp_path, timeout_seconds=15)
        # Verify status indicates either Docker or Local Fallback
        st = hybrid.status()
        assert "SANDBOX DURUMU" in st
        assert "HAZIR" in st

        # Execute canonical test command
        spec = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, ""))
        result = hybrid.execute(spec)
        assert isinstance(result, CommandExecutionResult)
        assert result.exit_code == 0


class TestPersistentReminders:
    def test_reminders_persisted_and_restored(self, tmp_path):
        reminders_file = str(tmp_path / "reminders.json")

        # 1. First service instance schedules a reminder
        svc1 = ReminderService(storage_path=reminders_file)
        item_id, msg = svc1.schedule(120, "Test Toplantısı")
        assert item_id > 0
        assert "Test Toplantısı" in msg
        assert os.path.exists(reminders_file)

        with open(reminders_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["label"] == "Test Toplantısı"

        # 2. Second service instance restores it on startup
        svc2 = ReminderService(storage_path=reminders_file)
        assert len(svc2._reminders) == 1
        restored = svc2._reminders[item_id]
        assert restored.label == "Test Toplantısı"
        assert restored.timer is not None

        # Clean up
        svc1.cancel_all()
        svc2.cancel_all()

    def test_cancel_all_updates_file(self, tmp_path):
        reminders_file = str(tmp_path / "reminders.json")
        svc = ReminderService(storage_path=reminders_file)
        svc.schedule(300, "Görev 1")
        svc.schedule(600, "Görev 2")
        assert len(svc._reminders) == 2

        msg = svc.cancel_all()
        assert "2 adet aktif hatırlatıcı iptal edildi" in msg
        assert len(svc._reminders) == 0

        with open(reminders_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 0


class TestAtomicNotesService:
    def test_atomic_save_and_backup(self, tmp_path):
        notes_file = str(tmp_path / "notes.json")
        svc = NotesService(notes_file=notes_file)

        ok, msg = svc.add_note("Önemli proje notu")
        assert ok is True
        assert "kaydedildi" in msg.lower()
        assert os.path.exists(notes_file)
        backup_file = str(Path(notes_file).with_suffix(".backup"))
        assert os.path.exists(backup_file)

        # Check content
        notes = svc._load()
        assert len(notes) == 1
        assert notes[0]["text"] == "Önemli proje notu"

    def test_corrupted_primary_recovers_from_backup(self, tmp_path):
        notes_file = str(tmp_path / "notes.json")
        svc = NotesService(notes_file=notes_file)
        svc.add_note("Kurtarılacak not")

        # Intentionally corrupt primary notes file
        with open(notes_file, "w", encoding="utf-8") as f:
            f.write("{invalid_json_content::;;")

        # Create new service instance - should recover from backup
        svc_recovered = NotesService(notes_file=notes_file)
        notes = svc_recovered._load()
        assert len(notes) == 1
        assert notes[0]["text"] == "Kurtarılacak not"


class TestDesktopOrganizerPreviewAndUndo:
    def test_preview_does_not_move_files(self, tmp_path):
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        doc = desktop / "belge.pdf"
        doc.write_text("pdf content", encoding="utf-8")
        pic = desktop / "resim.png"
        pic.write_text("png content", encoding="utf-8")

        journal = tmp_path / "journal.json"

        # Run with preview=True
        ok, msg, moved = organize_desktop(desktop_dir=desktop, preview=True, journal_file=journal)
        assert ok is True
        assert "Önizleme" in msg
        assert "2 dosya düzenlenecek" in msg

        # Verify files did NOT move
        assert doc.exists()
        assert pic.exists()
        assert not journal.exists()

    def test_organize_and_undo(self, tmp_path):
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        doc = desktop / "rapor.pdf"
        doc.write_text("rapor", encoding="utf-8")
        img = desktop / "manzara.jpg"
        img.write_text("manzara", encoding="utf-8")

        journal = tmp_path / "journal.json"

        # 1. Organize
        ok, msg, moved = organize_desktop(desktop_dir=desktop, preview=False, journal_file=journal)
        assert ok is True
        assert "düzenlendi" in msg.lower()
        assert not doc.exists()
        assert not img.exists()
        assert (desktop / "Belgeler" / "rapor.pdf").exists()
        assert (desktop / "Görseller" / "manzara.jpg").exists()
        assert journal.exists()

        # 2. Undo
        ok_undo, undo_msg = undo_organize_desktop(journal_file=journal)
        assert ok_undo is True
        assert "eski konumuna döndürüldü" in undo_msg.lower() or "geri" in undo_msg.lower()
        assert doc.exists()
        assert img.exists()
        assert not (desktop / "Belgeler" / "rapor.pdf").exists()
        assert not (desktop / "Görseller" / "manzara.jpg").exists()


class TestWebSearchFallback:
    def test_search_web_live_with_wikipedia_fallback(self):
        # Clear cache first
        _SEARCH_CACHE.clear()
        mock_summary = "Python, yüksek seviyeli, genel amaçlı bir programlama dilidir."

        with patch("ddgs.DDGS", side_effect=Exception("DDGS connection reset")), \
             patch("boru.tools.web_qa_tools.search_wikipedia_summary", return_value=(True, mock_summary)):
            ok, res = search_web_live("Python programlama dili nedir")
            assert ok is True
            assert "doğrulanmış web bilgisi" in res
            assert "Python" in res

    def test_search_web_live_empty_query(self):
        ok, res = search_web_live("   ")
        assert ok is False
        assert "belirtilmedi" in res
