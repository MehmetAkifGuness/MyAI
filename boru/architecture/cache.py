import hashlib
from collections import OrderedDict
from pathlib import Path
from threading import RLock

from boru.architecture.models import ArchitecturePlan
from boru.performance import PerformanceMonitor
from boru.tools.edit_contracts import SmartEditWorkspace
from boru.tools.edit_models import EditSource


class ProjectStatFingerprint:
    def __init__(self, root: str | Path) -> None:
        resolved = Path(root).resolve()
        if not resolved.is_dir():
            raise ValueError("Fingerprint kökü mevcut bir klasör olmalıdır.")
        self._root = resolved

    def build(self, paths: tuple[str, ...]) -> str:
        digest = hashlib.sha256()
        for relative_path in paths:
            target = (self._root / relative_path).resolve(strict=True)
            target.relative_to(self._root)
            stat = target.stat()
            digest.update(relative_path.encode("utf-8"))
            digest.update(
                f"\0{stat.st_size}\0{stat.st_mtime_ns}\0{stat.st_ino}\n".encode("ascii")
            )
        return digest.hexdigest()


class ArchitecturePlanCache:
    def __init__(self, max_entries: int = 32, monitor: PerformanceMonitor | None = None) -> None:
        if max_entries < 1:
            raise ValueError("Plan cache boyutu en az 1 olmalıdır.")
        self._entries: OrderedDict[tuple[str, str], ArchitecturePlan] = OrderedDict()
        self._max_entries = max_entries
        self._monitor = monitor
        self._lock = RLock()

    def get(self, task: str, fingerprint: str) -> ArchitecturePlan | None:
        key = (self._normalize_task(task), fingerprint)
        with self._lock:
            plan = self._entries.get(key)
            if plan is None:
                self._increment("architect.plan_cache.miss")
                return None
            self._entries.move_to_end(key)
            self._increment("architect.plan_cache.hit")
            return plan

    def put(self, task: str, fingerprint: str, plan: ArchitecturePlan) -> None:
        key = (self._normalize_task(task), fingerprint)
        with self._lock:
            self._entries[key] = plan
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def _increment(self, name: str) -> None:
        if self._monitor is not None:
            self._monitor.increment(name)

    @staticmethod
    def _normalize_task(task: str) -> str:
        return " ".join(task.casefold().split())


class CachingEditSourceWorkspace:
    def __init__(
        self,
        root: str | Path,
        delegate: SmartEditWorkspace,
        *,
        max_entries: int = 256,
        monitor: PerformanceMonitor | None = None,
    ) -> None:
        resolved = Path(root).resolve()
        if not resolved.is_dir() or max_entries < 1:
            raise ValueError("Kaynak cache yapılandırması geçersiz.")
        self._root = resolved
        self._delegate = delegate
        self._max_entries = max_entries
        self._monitor = monitor
        self._entries: OrderedDict[str, tuple[tuple[int, int, int], EditSource]] = OrderedDict()
        self._lock = RLock()

    def read_edit_source(self, relative_path: str) -> EditSource:
        signature = self._safe_signature(relative_path)
        if signature is not None:
            with self._lock:
                cached = self._entries.get(relative_path)
                if cached is not None and cached[0] == signature:
                    self._entries.move_to_end(relative_path)
                    self._increment("architect.source_cache.hit")
                    return cached[1]

        self._increment("architect.source_cache.miss")
        source = self._delegate.read_edit_source(relative_path)
        signature = self._safe_signature(relative_path)
        if signature is not None:
            with self._lock:
                self._entries[relative_path] = (signature, source)
                self._entries.move_to_end(relative_path)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
        return source

    def _safe_signature(self, relative_path: str) -> tuple[int, int, int] | None:
        try:
            normalized = relative_path.replace("\\", "/")
            parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
            if not parts or ".." in parts or normalized.startswith("/") or ":" in normalized:
                return None
            candidate = self._root.joinpath(*parts)
            current = self._root
            for part in parts:
                current = current / part
                if current.is_symlink():
                    return None
            target = candidate.resolve(strict=True)
            target.relative_to(self._root)
            if not target.is_file():
                return None
            stat = target.stat()
            return stat.st_size, stat.st_mtime_ns, stat.st_ino
        except (OSError, RuntimeError, ValueError):
            return None

    def _increment(self, name: str) -> None:
        if self._monitor is not None:
            self._monitor.increment(name)
