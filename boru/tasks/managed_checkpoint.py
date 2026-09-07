from dataclasses import replace
from pathlib import Path

from boru.tasks.checkpoint import JsonTaskCheckpointRepository, TaskCheckpoint
from boru.tasks.checkpoint_lock import CheckpointLease
from boru.tasks.checkpoint_storage import CheckpointStorage
from boru.tasks.execution_record import TaskExecutionRecord
from boru.tasks.checkpoint_validation import validate_payload_fields


class ManagedTaskCheckpointRepository(JsonTaskCheckpointRepository):
    """V3 envelope with validated backup, explicit recovery and project lease."""

    def __init__(self, file_path, *, lock_path=None):
        super().__init__(file_path)
        path = Path(file_path)
        self._lease = CheckpointLease(lock_path or path.with_name(path.name + ".lock"))
        self._disk = CheckpointStorage(path)
        self._last_document = None
        self.recovery_error = ""
        self._restore_token = None

    @property
    def schema_label(self):
        return "boru.task-checkpoint/v3"

    def close(self):
        self._lease.close()

    def _unpack(self, document):
        if not isinstance(document, dict):
            raise ValueError("Checkpoint kökü nesne olmalıdır.")
        if type(document.get("version")) is not int:
            raise ValueError("Checkpoint sürümü tamsayı olmalıdır.")
        if document["version"] != 3:
            migration = self._migrator.migrate(document)
            validate_payload_fields(migration.document)
            return self._decode(migration.document)
        if set(document) != {"schema", "version", "payload", "execution"}:
            raise ValueError("Checkpoint V3 alanları geçersiz.")
        if document["schema"] != "boru.task-checkpoint":
            raise ValueError("Checkpoint şeması geçersiz.")
        payload = self._migrator.migrate(document["payload"]).document
        validate_payload_fields(payload)
        checkpoint = self._decode(payload)
        execution = TaskExecutionRecord.from_dict(document["execution"])
        if execution is not None:
            identifiers = {task.task_id for task in checkpoint.plan.tasks} if checkpoint.plan else set()
            if not {key for key, _ in execution.attempts}.issubset(identifiers):
                raise ValueError("Deneme kaydı plan dışındaki task içeriyor.")
        return replace(checkpoint, execution=execution)

    def _pack(self, checkpoint):
        payload = self._encode(checkpoint)
        self._decode(payload)
        texts = [entry.note for entry in checkpoint.journal]
        if checkpoint.plan:
            texts.extend(path for task in checkpoint.plan.tasks for path in task.files)
        if any(pattern.search("\n".join(texts)) for pattern in self._SECRET_PATTERNS):
            raise ValueError("Hassas değer checkpoint günlüğüne yazılamaz.")
        document = {
            "schema": "boru.task-checkpoint", "version": 3, "payload": payload,
            "execution": checkpoint.execution.to_dict() if checkpoint.execution else None,
        }
        self._unpack(document)
        return document

    def load(self):
        self._last_migrated_from = None
        try:
            self._disk.ensure_current()
            if not self.path.exists():
                if self._disk.backup.exists():
                    raise ValueError("Ana checkpoint eksik; yedekten geri yükleme gerekli.")
                return TaskCheckpoint(None)
            document = self._disk.read(self.path)
            checkpoint = self._unpack(document)
            if document["version"] != 3:
                converted = self._pack(checkpoint)
                self._disk.commit(converted, previous=document)
                self._last_migrated_from = document["version"]
                document = converted
            self._last_document = document
            self.recovery_error = ""
            return checkpoint
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
            self.recovery_error = f"[CHECKPOINT_INVALID] {error}"
            return TaskCheckpoint(None)

    def ensure_writable(self):
        if self.recovery_error:
            raise RuntimeError(self.recovery_error + " 'checkpoint durumu' ile inceleyin.")
        self._disk.ensure_current()

    def save(self, checkpoint):
        self.ensure_writable()
        document = self._pack(checkpoint)
        self._disk.commit(document, previous=self._last_document or document)
        self._last_document = document

    def status(self):
        return (
            "CHECKPOINT DURUMU\n" + (self.recovery_error or "Durum: HAZIR")
            + f"\nŞema: {self.schema_label}\nDosya: {self.path}"
            + f"\nYedek: {'var' if self._disk.backup.exists() else 'yok'}"
            + "\nProje kilidi: bu oturumda; geri yükleme açık onay gerektirir."
        )

    def prepare_restore(self):
        self._disk.ensure_current()
        backup = self._disk.read(self._disk.backup)
        checkpoint = self._unpack(backup)
        # Never silently downgrade an unknown future primary schema.
        if self.path.exists():
            try:
                current = self._disk.read(self.path)
            except (OSError, RuntimeError, ValueError):
                current = None
            if isinstance(current, dict) and current.get("version") not in (1, 2, 3):
                raise ValueError("Bilinmeyen sürüm geri yüklemeyle düşürülemez.")
        self._restore_token = (self._disk.expected, self._disk.digest(self._disk.backup))
        objective = checkpoint.plan.objective if checkpoint.plan else "boş plan"
        return (
            f"CHECKPOINT GERİ YÜKLEME ÖNERİSİ\nHedef: {objective}\n"
            "Yedek önceki görev durumunu içerir; kaynak kod geri alınmaz.\n"
            "Uygulamak için 'checkpoint geri yüklemeyi onayla', vazgeçmek için 'iptal' yazın."
        )

    def cancel_restore(self):
        self._restore_token = None

    def restore(self):
        token, self._restore_token = self._restore_token, None
        current = (self._disk.digest(self.path), self._disk.digest(self._disk.backup))
        if token is None or token != current:
            raise ValueError("Geri yükleme önerisi yok veya dosyalar onaydan sonra değişti.")
        backup = self._disk.read(self._disk.backup)
        checkpoint = self._unpack(backup)
        document = self._pack(checkpoint)
        preserved = self._disk.preserve_damaged()
        self._disk.commit(document)
        self._last_document = document
        self.recovery_error = ""
        return preserved

    def archive_current(self, checkpoint):
        self.ensure_writable()
        return self._disk.archive_document(self._pack(checkpoint))

    def list_archives(self):
        directory = self._disk.archive
        if directory.is_symlink():
            raise ValueError("Arşiv dizini sembolik bağlantı olamaz.")
        if not directory.exists():
            return "GÖREV ARŞİVİ\nKayıt: 0"
        paths = sorted(directory.glob("*.json"))[:50]
        lines = ["GÖREV ARŞİVİ", f"Kayıt: {len(paths)}"]
        for path in paths:
            checkpoint = self._unpack(self._disk.read(path))
            plan = checkpoint.plan
            if plan:
                lines.append(f"- {path.stem}: {plan.objective}")
        return "\n".join(lines)
