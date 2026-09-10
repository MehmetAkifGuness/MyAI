import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from boru.evaluation.models import Verdict
from boru.tools.workspace import WorkspacePathResolver


class VerifiedTaskExperience:
    """Repo-isolated, bounded verification metadata, not training or executable memory."""

    SCHEMA = 'boru.verified-experience/v1'

    def __init__(self, root: Path, storage: Path):
        self.root = root.resolve()
        self.key = hashlib.sha256(str(self.root).encode()).hexdigest()
        self.storage = storage
        self.lock = RLock()

    def read(self):
        try:
            if self.storage.is_symlink() or self.storage.stat().st_size > 256000:
                return []
            data = json.loads(self.storage.read_text(encoding='utf-8'))
            if data.get('schema') != self.SCHEMA or data.get('root') != self.key:
                return []
            rows = data.get('records')
            if not isinstance(rows, list):
                return []
            return [r for r in rows[-100:] if self._valid(r)]
        except (OSError, ValueError, AttributeError):
            return []

    def _valid(self, row):
        if not isinstance(row, dict) or set(row) != {'paths', 'fingerprints', 'route'}:
            return False
        if row['route'] not in {'primary', 'fallback'} or not isinstance(row['paths'], list):
            return False
        if not isinstance(row['fingerprints'], dict) or not 1 <= len(row['fingerprints']) <= 50:
            return False
        try:
            resolver = WorkspacePathResolver(self.root)
            for path, digest in row['fingerprints'].items():
                if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                    return False
                resolver.resolve(path)
            return set(row['paths']) <= set(row['fingerprints'])
        except (OSError, ValueError, RuntimeError, TypeError):
            return False

    def record(self, report, evaluator, route='primary'):
        if report is None or report.verdict is not Verdict.PASS or not evaluator.is_current(report):
            return False
        if not any(c.name == 'Test' and c.verdict is Verdict.PASS for c in report.checks):
            return False
        row = {'paths': list(report.paths), 'fingerprints': dict(report.fingerprints), 'route': route}
        if not self._valid(row):
            return False
        with self.lock:
            records = [r for r in self.read() if r != row]
            records.append(row)
            self.storage.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.storage.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump({'schema': self.SCHEMA, 'root': self.key, 'records': records[-100:]}, stream)
                os.replace(temporary, self.storage)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return True

    def recall(self, candidates):
        from boru.tools.workspace import ReadOnlyWorkspace
        reader = ReadOnlyWorkspace(self.root)
        result = []
        for row in reversed(self.read()):
            if not set(row['paths']) & set(candidates):
                continue
            try:
                current = all(
                    hashlib.sha256(reader.read_text_file(p).encode('utf-8')).hexdigest() == digest
                    for p, digest in row['fingerprints'].items()
                )
            except (OSError, ValueError, RuntimeError):
                current = False
            if current:
                result.append({'previously_verified': row['paths'], 'route': row['route']})
            if len(result) == 3:
                break
        return result
