"""
Tests for BoruDatabase SQLite + WAL persistence and legacy data migration.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from boru.persistence.database import BoruDatabase


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_boru.db"
    db = BoruDatabase(db_path=db_file)
    return db


class TestBoruDatabase:
    def test_schema_and_wal_mode(self, temp_db):
        with temp_db.get_connection() as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            # On memory/temp DB on Windows, WAL is set
            assert mode.lower() in ("wal", "memory")

            # Check tables exist
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
            assert "notes" in tables
            assert "reminders" in tables
            assert "desktop_cleanup_journal" in tables
            assert "key_value_store" in tables

    def test_notes_crud(self, temp_db):
        # 1. Add Note
        entry = temp_db.add_note("Proje mimarisi toplantısı", date_str="12 Eylül 16:30", tags=["proje", "mimari"])
        assert entry["id"] == 1
        assert entry["text"] == "Proje mimarisi toplantısı"
        assert entry["tags"] == ["proje", "mimari"]

        # 2. Get Notes
        notes = temp_db.get_notes()
        assert len(notes) == 1
        assert notes[0]["text"] == "Proje mimarisi toplantısı"

        # 3. Get Last Note
        last = temp_db.get_last_note()
        assert last is not None
        assert last["text"] == "Proje mimarisi toplantısı"

        # 4. Clear Notes
        cleared = temp_db.clear_notes()
        assert cleared == 1
        assert len(temp_db.get_notes()) == 0

    def test_reminders_crud(self, temp_db):
        now = time.time()
        # 1. Save Reminder
        r_id = temp_db.save_reminder(due_at=now + 120, label="Fırını kapat")
        assert r_id > 0

        # 2. Get Active Reminders
        active = temp_db.get_active_reminders()
        assert len(active) == 1
        assert active[0]["label"] == "Fırını kapat"

        # 3. Mark Fired
        temp_db.mark_reminder_fired(r_id)
        assert len(temp_db.get_active_reminders()) == 0

        # 4. Cancel All
        temp_db.save_reminder(due_at=now + 300, label="Mola")
        temp_db.save_reminder(due_at=now + 600, label="Su iç")
        assert len(temp_db.get_active_reminders()) == 2
        cancelled = temp_db.cancel_all_reminders()
        assert cancelled == 2
        assert len(temp_db.get_active_reminders()) == 0

    def test_desktop_cleanup_journal(self, temp_db):
        entries = [
            {"source": "C:/Desktop/a.pdf", "destination": "C:/Desktop/Belgeler/a.pdf", "category": "Belgeler"},
            {"source": "C:/Desktop/b.png", "destination": "C:/Desktop/Görseller/b.png", "category": "Görseller"},
        ]
        temp_db.add_cleanup_entries(entries)

        retrieved = temp_db.get_cleanup_entries()
        assert len(retrieved) == 2
        assert retrieved[0]["source"] == "C:/Desktop/a.pdf"

        cleared = temp_db.clear_cleanup_journal()
        assert cleared == 2
        assert len(temp_db.get_cleanup_entries()) == 0

    def test_key_value_store(self, temp_db):
        temp_db.set_kv("learning", "user_prefs", {"theme": "dark", "lang": "tr"})
        val = temp_db.get_kv("learning", "user_prefs")
        assert val == {"theme": "dark", "lang": "tr"}

        temp_db.set_kv("learning", "rules", ["rule_1", "rule_2"])
        ns_data = temp_db.get_namespace("learning")
        assert "user_prefs" in ns_data
        assert "rules" in ns_data

    def test_auto_migrate_from_legacy_files(self, tmp_path):
        db_file = tmp_path / "migrated.db"
        db = BoruDatabase(db_path=db_file)

        # Create dummy legacy files
        notes_file = tmp_path / "user_notes.json"
        notes_file.write_text(json.dumps([{"text": "Eski not 1", "date_str": "12 Eylül"}]), encoding="utf-8")

        reminders_dir = tmp_path / "data"
        reminders_dir.mkdir()
        reminders_file = reminders_dir / "reminders.json"
        reminders_file.write_text(json.dumps([{"id": 10, "due_at": time.time() + 600, "label": "Eski hatırlatıcı"}]), encoding="utf-8")

        journal_file = reminders_dir / "desktop_cleanup_journal.json"
        journal_file.write_text(json.dumps([{"source": "s.txt", "destination": "d.txt", "category": "Belgeler"}]), encoding="utf-8")

        counts = db.auto_migrate_from_legacy_files(project_root=tmp_path)
        assert counts["notes"] == 1
        assert counts["reminders"] == 1
        assert counts["journal"] == 1

        # Check DB content
        assert len(db.get_notes()) == 1
        assert db.get_notes()[0]["text"] == "Eski not 1"
        assert len(db.get_active_reminders()) == 1
        assert len(db.get_cleanup_entries()) == 1

