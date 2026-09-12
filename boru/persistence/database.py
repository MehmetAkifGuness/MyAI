"""
boru.persistence.database
=========================
Merkezi, ACID uyumlu, yüksek performanslı SQLite + WAL modunda veritabanı motoru.
Dağınık JSON dosyalarını güvenli ve atomik bir ilişkisel veritabanı çatısı altında toplar.
Elektrik kesintileri veya eşzamanlı çoklu thread erişimlerinde tam veri bütünlüğü sunar.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "boru.db"


class BoruDatabase:
    """
    Börü AI Merkezi SQLite Veritabanı Yöneticisi.
    WAL (Write-Ahead Logging) modu ile okuma ve yazma işlemlerinde sıfır kilitlenme sağlar.
    """

    _instance: Optional[BoruDatabase] = None
    _lock = threading.Lock()

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    @classmethod
    def get_instance(cls, db_path: Path | str | None = None) -> BoruDatabase:
        with cls._lock:
            if cls._instance is None:
                cls._instance = BoruDatabase(db_path)
            return cls._instance

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """İş parçacığı (thread) bazlı güvenli bağlantı sağlar."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        try:
            # WAL modu ve performans pragma ayarları
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Veritabanı tablolarını ve indekslerini oluşturur."""
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    date_str TEXT,
                    timestamp REAL NOT NULL,
                    tags TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    due_at REAL NOT NULL,
                    label TEXT NOT NULL,
                    is_fired INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS desktop_cleanup_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    category TEXT,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS key_value_store (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (namespace, key)
                );

                CREATE INDEX IF NOT EXISTS idx_notes_ts ON notes(timestamp);
                CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at, is_fired);
                CREATE INDEX IF NOT EXISTS idx_journal_ts ON desktop_cleanup_journal(timestamp);
            """)

    # ── Notes API ────────────────────────────────────────────────────────────
    def add_note(self, text: str, date_str: str = "", timestamp: float | None = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        ts = timestamp or time.time()
        tags_str = ",".join(tags) if tags else ""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO notes (text, date_str, timestamp, tags) VALUES (?, ?, ?, ?)",
                (text, date_str, ts, tags_str),
            )
            note_id = cursor.lastrowid
            return {
                "id": note_id,
                "text": text,
                "date_str": date_str,
                "timestamp": ts,
                "tags": tags or [],
            }

    def get_notes(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT id, text, date_str, timestamp, tags FROM notes ORDER BY id ASC").fetchall()
            result = []
            for r in rows:
                tag_list = [t for t in r["tags"].split(",") if t] if r["tags"] else []
                result.append({
                    "id": r["id"],
                    "text": r["text"],
                    "date_str": r["date_str"],
                    "timestamp": r["timestamp"],
                    "tags": tag_list,
                })
            return result

    def get_last_note(self) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            r = conn.execute("SELECT id, text, date_str, timestamp, tags FROM notes ORDER BY id DESC LIMIT 1").fetchone()
            if not r:
                return None
            tag_list = [t for t in r["tags"].split(",") if t] if r["tags"] else []
            return {
                "id": r["id"],
                "text": r["text"],
                "date_str": r["date_str"],
                "timestamp": r["timestamp"],
                "tags": tag_list,
            }

    def clear_notes(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM notes")
            return cursor.rowcount

    # ── Reminders API ────────────────────────────────────────────────────────
    def save_reminder(self, due_at: float, label: str, custom_id: Optional[int] = None) -> int:
        with self.get_connection() as conn:
            now = time.time()
            if custom_id is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO reminders (id, due_at, label, is_fired, created_at) VALUES (?, ?, ?, 0, ?)",
                    (custom_id, due_at, label, now),
                )
                return custom_id
            else:
                cursor = conn.execute(
                    "INSERT INTO reminders (due_at, label, is_fired, created_at) VALUES (?, ?, 0, ?)",
                    (due_at, label, now),
                )
                return cursor.lastrowid

    def get_active_reminders(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            now = time.time()
            rows = conn.execute(
                "SELECT id, due_at, label, created_at FROM reminders WHERE is_fired = 0 AND due_at > ? ORDER BY due_at ASC",
                (now,),
            ).fetchall()
            return [{"id": r["id"], "due_at": r["due_at"], "label": r["label"]} for r in rows]

    def mark_reminder_fired(self, reminder_id: int) -> None:
        with self.get_connection() as conn:
            conn.execute("UPDATE reminders SET is_fired = 1 WHERE id = ?", (reminder_id,))

    def delete_reminder(self, reminder_id: int) -> None:
        with self.get_connection() as conn:
            conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    def cancel_all_reminders(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM reminders WHERE is_fired = 0")
            return cursor.rowcount

    # ── Desktop Journal API ──────────────────────────────────────────────────
    def add_cleanup_entries(self, entries: List[Dict[str, Any]]) -> None:
        with self.get_connection() as conn:
            for entry in entries:
                conn.execute(
                    "INSERT INTO desktop_cleanup_journal (source, destination, category, timestamp) VALUES (?, ?, ?, ?)",
                    (
                        str(entry.get("source", "")),
                        str(entry.get("destination", "")),
                        str(entry.get("category", "")),
                        float(entry.get("timestamp", time.time())),
                    ),
                )

    def get_cleanup_entries(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT source, destination, category, timestamp FROM desktop_cleanup_journal ORDER BY id ASC"
            ).fetchall()
            return [
                {
                    "source": r["source"],
                    "destination": r["destination"],
                    "category": r["category"],
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]

    def clear_cleanup_journal(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM desktop_cleanup_journal")
            return cursor.rowcount

    # ── Key-Value / Learning Store API ───────────────────────────────────────
    def set_kv(self, namespace: str, key: str, value: Any) -> None:
        val_json = json.dumps(value, ensure_ascii=False)
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO key_value_store (namespace, key, value_json, updated_at) VALUES (?, ?, ?, ?)",
                (namespace, key, val_json, time.time()),
            )

    def get_kv(self, namespace: str, key: str, default: Any = None) -> Any:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM key_value_store WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value_json"])
            except Exception:
                return default

    def get_namespace(self, namespace: str) -> Dict[str, Any]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value_json FROM key_value_store WHERE namespace = ?",
                (namespace,),
            ).fetchall()
            result = {}
            for r in rows:
                try:
                    result[r["key"]] = json.loads(r["value_json"])
                except Exception:
                    result[r["key"]] = r["value_json"]
            return result

    # ── Otomatik Eski JSON Veri Göçü (Auto Migration) ────────────────────────
    def auto_migrate_from_legacy_files(self, project_root: Optional[Path] = None) -> Dict[str, int]:
        """Eski dağınık JSON dosyalarından SQLite'a tek seferlik veri göçü yapar."""
        root = project_root or Path(__file__).resolve().parent.parent.parent
        counts = {"notes": 0, "reminders": 0, "journal": 0, "learning": 0}

        # 1. user_notes.json
        legacy_notes = root / "user_notes.json"
        if legacy_notes.exists():
            try:
                with open(legacy_notes, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and len(self.get_notes()) == 0:
                    for item in data:
                        text = item.get("text", "").strip()
                        if text:
                            self.add_note(
                                text=text,
                                date_str=item.get("date_str", ""),
                                timestamp=item.get("timestamp"),
                            )
                            counts["notes"] += 1
            except Exception as e:
                logger.debug(f"Notes göç hatası: {e}")

        # 2. data/reminders.json
        legacy_reminders = root / "data" / "reminders.json"
        if legacy_reminders.exists():
            try:
                with open(legacy_reminders, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and len(self.get_active_reminders()) == 0:
                    now = time.time()
                    for item in data:
                        due_at = float(item.get("due_at", 0))
                        if due_at > now:
                            self.save_reminder(
                                due_at=due_at,
                                label=item.get("label", "Hatırlatıcı"),
                                custom_id=item.get("id"),
                            )
                            counts["reminders"] += 1
            except Exception as e:
                logger.debug(f"Reminders göç hatası: {e}")

        # 3. data/desktop_cleanup_journal.json
        legacy_journal = root / "data" / "desktop_cleanup_journal.json"
        if legacy_journal.exists():
            try:
                with open(legacy_journal, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and len(self.get_cleanup_entries()) == 0:
                    self.add_cleanup_entries(data)
                    counts["journal"] += len(data)
            except Exception as e:
                logger.debug(f"Journal göç hatası: {e}")

        # 4. Öğrenme verileri (reflection, curiosity, continuous, user_understanding)
        learning_files = {
            "reflection_rules": root / "data" / "reflection_rules.json",
            "curiosity": root / "data" / "curiosity_knowledge.json",
            "continuous": root / "data" / "continuous_knowledge.json",
            "user_understanding": root / "data" / "user_understanding.json",
        }
        for ns, path in learning_files.items():
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.set_kv("learning", ns, data)
                    counts["learning"] += 1
                except Exception as e:
                    logger.debug(f"Learning ({ns}) göç hatası: {e}")

        logger.info(f"SQLite otomatik veri göçü tamamlandı: {counts}")
        return counts

