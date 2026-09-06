import re
import sqlite3
from pathlib import Path

from boru.database_tools.models import DatabaseResult
from boru.tools.workspace import WorkspacePathResolver


class ReadOnlySqliteService:
    _ALLOWED_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
    _QUERY_PREFIX = re.compile(r"^\s*(?:select|with|explain\s+(?:query\s+plan\s+)?select)\b", re.I)

    def __init__(
        self,
        workspace_root: str | Path,
        max_rows: int = 100,
        max_cell_characters: int = 300,
        progress_steps: int = 250_000,
    ):
        if min(max_rows, max_cell_characters, progress_steps) < 1:
            raise ValueError("Veritabanı okuma sınırları pozitif olmalıdır.")
        self._resolver = WorkspacePathResolver(workspace_root)
        self._max_rows = max_rows
        self._max_cell_characters = max_cell_characters
        self._progress_steps = progress_steps

    def list_tables(self, database_path: str) -> DatabaseResult:
        connection = self._connect(database_path)
        try:
            cursor = connection.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            return self._result(cursor)
        except sqlite3.DatabaseError as error:
            raise ValueError(f"SQLite tabloları okunamadı: {error}") from error
        finally:
            connection.close()

    def schema(self, database_path: str) -> DatabaseResult:
        connection = self._connect(database_path)
        try:
            cursor = connection.execute(
                "SELECT name, type, sql FROM sqlite_master "
                "WHERE type IN ('table','view','index') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            return self._result(cursor)
        except sqlite3.DatabaseError as error:
            raise ValueError(f"SQLite şeması okunamadı: {error}") from error
        finally:
            connection.close()

    def describe(self, database_path: str, table_name: str) -> DatabaseResult:
        cleaned_name = table_name.strip()
        if not cleaned_name or len(cleaned_name) > 128 or "\x00" in cleaned_name:
            raise ValueError("Tablo adı geçersiz.")
        connection = self._connect(database_path)
        try:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table','view')",
                (cleaned_name,),
            ).fetchone()
            if exists is None:
                raise ValueError(f"Tablo veya görünüm bulunamadı: {cleaned_name}")
            cursor = connection.execute(
                "SELECT cid, name, type, \"notnull\", dflt_value, pk FROM pragma_table_info(?)",
                (cleaned_name,),
            )
            return self._result(cursor)
        except sqlite3.DatabaseError as error:
            raise ValueError(f"SQLite tablo bilgisi okunamadı: {error}") from error
        finally:
            connection.close()

    def query(self, database_path: str, sql: str) -> DatabaseResult:
        cleaned_sql = sql.strip()
        if not cleaned_sql or len(cleaned_sql) > 20_000:
            raise ValueError("SQL sorgusu boş veya izin verilen sınırın üzerinde.")
        if self._QUERY_PREFIX.match(cleaned_sql) is None:
            raise ValueError("Yalnızca SELECT, WITH veya EXPLAIN SELECT sorgularına izin verilir.")

        connection = self._connect(database_path)
        try:
            connection.set_authorizer(self._authorize_read)
            remaining_steps = self._progress_steps

            def check_progress():
                nonlocal remaining_steps
                remaining_steps -= 1000
                return 1 if remaining_steps <= 0 else 0

            connection.set_progress_handler(check_progress, 1000)
            try:
                cursor = connection.execute(cleaned_sql)
                return self._result(cursor)
            except sqlite3.DatabaseError as error:
                raise ValueError(f"Salt-okunur SQL sorgusu çalıştırılamadı: {error}") from error
        finally:
            connection.close()

    def _connect(self, database_path: str) -> sqlite3.Connection:
        target = self._resolver.resolve(database_path)
        if not target.is_file() or target.suffix.casefold() not in self._ALLOWED_SUFFIXES:
            raise ValueError("Hedef, workspace içindeki bir SQLite veritabanı olmalıdır.")
        connection = None
        try:
            connection = sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True, timeout=2.0)
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as error:
            if connection is not None:
                connection.close()
            raise ValueError(f"SQLite veritabanı salt-okunur açılamadı: {error}") from error

    def _result(self, cursor: sqlite3.Cursor) -> DatabaseResult:
        columns = tuple(item[0] for item in (cursor.description or ()))
        raw_rows = cursor.fetchmany(self._max_rows + 1)
        truncated = len(raw_rows) > self._max_rows
        rows = tuple(
            tuple(self._format_cell(value) for value in row)
            for row in raw_rows[: self._max_rows]
        )
        return DatabaseResult(columns, rows, truncated)

    def _format_cell(self, value) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bytes):
            return f"[BLOB {len(value)} bayt]"
        text = " ".join(str(value).split())
        if len(text) > self._max_cell_characters:
            return text[: self._max_cell_characters] + "…"
        return text

    @staticmethod
    def _authorize_read(action, arg1, arg2, database_name, trigger_name):
        del arg1, arg2, database_name, trigger_name
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            getattr(sqlite3, "SQLITE_RECURSIVE", -1),
        }
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
