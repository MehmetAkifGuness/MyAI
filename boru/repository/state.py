import json
from datetime import datetime, timezone
from pathlib import Path


class RepositoryWorkspaceState:
    SCHEMA = "boru.repository-workspace/v1"

    def __init__(self, path: Path):
        self._path = path

    def load(self) -> str | None:
        if not self._path.is_file():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or data.get("schema") != self.SCHEMA:
            return None
        root = data.get("root")
        return root if isinstance(root, str) and root else None

    def save(self, relative_root: str) -> None:
        self._write({"schema": self.SCHEMA, "root": relative_root})

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)


class RepositoryAuditLog:
    def __init__(self, path: Path, *, max_records: int = 500):
        self._path = path
        self._max_records = max_records

    def record(self, event: str, root: str, detail: str = "") -> None:
        try:
            records = self.read()
            records.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "root": root,
                "detail": detail[:1000],
            })
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(self._path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(records[-self._max_records:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self._path)
        except OSError:
            return

    def read(self) -> list[dict]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
