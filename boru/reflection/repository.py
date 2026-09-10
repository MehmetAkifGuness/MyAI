from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from boru.reflection.models import ReflectionRecord


class JsonReflectionRepository:
    """Thread-safe, atomic JSON storage for self-improvement reflection records."""

    SCHEMA = "boru.reflection-memory/v1"

    def __init__(self, storage_path: Path, max_records: int = 100):
        self.storage_path = storage_path.resolve()
        self.max_records = max_records
        self._lock = RLock()

    def read_records(self) -> list[ReflectionRecord]:
        with self._lock:
            if not self.storage_path.exists():
                return []
            try:
                if self.storage_path.is_symlink() or self.storage_path.stat().st_size > 512_000:
                    return []
                raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if raw.get("schema") != self.SCHEMA:
                    return []
                items = raw.get("records", [])
                if not isinstance(items, list):
                    return []
                return [ReflectionRecord.from_dict(item) for item in items if isinstance(item, dict)]
            except (OSError, ValueError, KeyError):
                return []

    def save_record(self, record: ReflectionRecord) -> bool:
        with self._lock:
            records = self.read_records()
            # Aynı id varsa güncelle, yoksa ekle
            filtered = [r for r in records if r.id != record.id]
            filtered.append(record)
            trimmed = filtered[-self.max_records:]

            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.storage_path.parent,
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    payload = {
                        "schema": self.SCHEMA,
                        "records": [r.to_dict() for r in trimmed],
                    }
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
                os.replace(temporary, self.storage_path)
                return True
            except OSError:
                return False
            finally:
                if temporary is not None and temporary.exists():
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass

    def query_by_paths(self, paths: tuple[str, ...], max_results: int = 5) -> list[ReflectionRecord]:
        """Verilen dosya yollarıyla ilgili en güncel dersleri geriye doğru döndürür."""
        if not paths:
            return []
        normalized_targets = {p.replace("\\", "/").casefold() for p in paths}
        results: list[ReflectionRecord] = []

        for record in reversed(self.read_records()):
            record_paths = {p.replace("\\", "/").casefold() for p in record.target_paths}
            if record_paths & normalized_targets:
                results.append(record)
                if len(results) >= max_results:
                    break

        return results
