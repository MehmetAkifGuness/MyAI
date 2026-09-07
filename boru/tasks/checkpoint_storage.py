import hashlib
import json
from pathlib import Path
from uuid import uuid4

from boru.persistence import AtomicJsonFileStore


class CheckpointStorage:
    """Bounded disk operations and compare-before-write for task documents."""

    MAX_BYTES = 256 * 1024

    def __init__(self, path: Path):
        self.path = path
        self.backup = path.with_name(path.name + ".backup")
        self.archive = path.parent / (path.stem + "_archive")
        self.expected = self.digest(path)

    @staticmethod
    def digest(path):
        if path.is_symlink():
            raise ValueError("Checkpoint sembolik bağlantı olamaz.")
        if not path.exists():
            return None
        if path.stat().st_size > CheckpointStorage.MAX_BYTES:
            return "oversized"
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def read(self, path):
        if path.is_symlink() or path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Checkpoint yolu veya boyutu geçersiz.")
        value = AtomicJsonFileStore(path).read()
        if value is None:
            raise ValueError("Checkpoint boş veya JSON null.")
        return value

    def ensure_current(self):
        if self.digest(self.path) != self.expected:
            raise RuntimeError("[CHECKPOINT_CHANGED] Checkpoint dışarıdan değişti; uygulamayı yeniden başlatın.")

    def write(self, path, document):
        if path.is_symlink():
            raise ValueError("Checkpoint hedefi sembolik bağlantı olamaz.")
        encoded = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if len(encoded.encode("utf-8")) > self.MAX_BYTES:
            raise ValueError("Checkpoint yazma boyut sınırını aşıyor.")
        AtomicJsonFileStore(path).write(document)

    def commit(self, document, previous=None):
        self.ensure_current()
        if previous is not None:
            self.write(self.backup, previous)
        self.write(self.path, document)
        self.expected = self.digest(self.path)

    def archive_document(self, document):
        if self.archive.is_symlink():
            raise ValueError("Arşiv dizini sembolik bağlantı olamaz.")
        self.archive.mkdir(parents=True, exist_ok=True)
        entries = list(self.archive.iterdir())
        if len(entries) >= 50:
            raise ValueError("Arşiv sınırı 50 kayıt; mevcut arşivleri dışarı taşıyın.")
        identifier = uuid4().hex
        self.write(self.archive / (identifier + ".json"), document)
        return identifier

    def preserve_damaged(self):
        if not self.path.exists():
            return None
        if self.path.is_symlink() or self.path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Bozuk checkpoint güvenli boyutta değil; elle inceleme gerekli.")
        target = self.path.with_name(self.path.name + ".damaged-" + uuid4().hex)
        with target.open("xb") as handle:
            handle.write(self.path.read_bytes())
        return target
