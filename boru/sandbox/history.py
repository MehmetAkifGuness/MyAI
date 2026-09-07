from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from boru.persistence import AtomicJsonFileStore, JsonFileReadError, JsonFileWriteError


@dataclass(frozen=True, slots=True)
class TerminalHistoryEntry:
    sequence: int
    command: str
    working_directory: str
    status: str
    exit_code: int | None


class TerminalHistory:
    """Persist a bounded audit of canonical commands, without raw user input."""

    _MAX_ENTRIES = 50

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._store = AtomicJsonFileStore(path)
        self._lock = RLock()

    def append(self, command, working_directory, status, exit_code):
        with self._lock:
            entries = list(self._load())
            sequence = entries[-1].sequence + 1 if entries else 1
            entries.append(
                TerminalHistoryEntry(
                    sequence,
                    command[:1000],
                    working_directory[:500],
                    status[:50],
                    exit_code,
                )
            )
            entries = entries[-self._MAX_ENTRIES :]
            try:
                self._store.write({"version": 1, "entries": [self._encode(x) for x in entries]})
            except JsonFileWriteError as error:
                raise RuntimeError("Terminal geçmişi yazılamadı.") from error

    def render(self):
        entries = self._load()
        lines = ["TERMİNAL GEÇMİŞİ", f"Kayıt: {len(entries)}"]
        for item in entries[-20:]:
            cwd = item.working_directory or "."
            lines.append(
                f"- #{item.sequence} [{item.status}] ({cwd}) {item.command}; çıkış={item.exit_code}"
            )
        return "\n".join(lines)

    def _load(self):
        if self._path.is_symlink():
            raise ValueError("Terminal geçmişi sembolik bağlantı olamaz.")
        if self._path.exists() and self._path.stat().st_size > 128 * 1024:
            raise ValueError("Terminal geçmişi boyut sınırını aşıyor.")
        try:
            data = self._store.read()
        except JsonFileReadError as error:
            raise RuntimeError("Terminal geçmişi okunamadı.") from error
        if data is None:
            return ()
        return self._decode_document(data)

    def _decode_document(self, data):
        if not isinstance(data, dict) or set(data) != {"version", "entries"}:
            raise ValueError("Terminal geçmişi biçimi geçersiz.")
        if data["version"] != 1 or not isinstance(data["entries"], list):
            raise ValueError("Terminal geçmişi sürümü veya kayıtları geçersiz.")
        if len(data["entries"]) > self._MAX_ENTRIES:
            raise ValueError("Terminal geçmişi kayıt sınırını aşıyor.")
        return tuple(self._decode(item) for item in data["entries"])

    @staticmethod
    def _encode(item):
        return {
            "sequence": item.sequence,
            "command": item.command,
            "working_directory": item.working_directory,
            "status": item.status,
            "exit_code": item.exit_code,
        }

    @staticmethod
    def _decode(item):
        if not isinstance(item, dict) or set(item) != {
            "sequence", "command", "working_directory", "status", "exit_code"
        }:
            raise ValueError("Terminal geçmişi kaydı geçersiz.")
        sequence = item["sequence"]
        exit_code = item["exit_code"]
        texts = (item["command"], item["working_directory"], item["status"])
        if type(sequence) is not int or sequence < 1:
            raise ValueError("Terminal geçmişi sıra numarası geçersiz.")
        if exit_code is not None and type(exit_code) is not int:
            raise ValueError("Terminal geçmişi çıkış kodu geçersiz.")
        if not all(isinstance(value, str) for value in texts):
            raise ValueError("Terminal geçmişi metin alanı geçersiz.")
        return TerminalHistoryEntry(sequence, *texts, exit_code)
