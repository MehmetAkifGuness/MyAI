import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from boru.tools.workspace import WorkspaceAccessError, WorkspacePathResolver


@dataclass(frozen=True, slots=True)
class TaskSourceFingerprint:
    path: str
    sha256: str

    def __post_init__(self) -> None:
        path = self.path.strip().replace("\\", "/")
        digest = self.sha256.strip().casefold()
        if not path:
            raise ValueError("Task kaynak yolu boş olamaz.")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("Task kaynak SHA-256 değeri geçersiz.")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "sha256", digest)


@dataclass(frozen=True, slots=True)
class TaskSourceDrift:
    path: str
    expected_sha256: str
    current_sha256: str | None


class TaskSourceDriftError(ValueError):
    def __init__(
        self,
        drifts: tuple[TaskSourceDrift, ...],
        *,
        missing_baseline: bool = False,
    ) -> None:
        self.drifts = drifts
        self.missing_baseline = missing_baseline
        if missing_baseline:
            message = (
                "Checkpoint kaynak özeti içermiyor; eski plan güvenli biçimde çalıştırılamaz. "
                "Görevi yeniden planlayın."
            )
        else:
            details = ", ".join(
                f"{item.path} (beklenen {item.expected_sha256[:12]}, "
                f"mevcut {(item.current_sha256 or 'DOSYA YOK')[:12]})"
                for item in drifts
            )
            message = (
                f"Plan oluşturulduktan sonra kaynak değişti: {details}. "
                "Eski plan durduruldu; güncel kaynakla yeniden görev planlayın."
            )
        super().__init__(message)


class TaskSourceFingerprintGuard:
    """Hashes bounded task files while enforcing the workspace path policy."""

    def __init__(self, root: str | Path, *, max_file_bytes: int = 2 * 1024 * 1024) -> None:
        if max_file_bytes < 1:
            raise ValueError("Task kaynak boyut sınırı pozitif olmalıdır.")
        self._resolver = WorkspacePathResolver(root)
        self._max_file_bytes = max_file_bytes

    def snapshot(self, paths: tuple[str, ...]) -> tuple[TaskSourceFingerprint, ...]:
        normalized = tuple(
            dict.fromkeys(
                path.strip().replace("\\", "/")
                for path in paths
                if path.strip()
            )
        )
        return tuple(
            TaskSourceFingerprint(path, self._hash_required(path))
            for path in normalized
        )

    def compare(
        self,
        expected: tuple[TaskSourceFingerprint, ...],
    ) -> tuple[TaskSourceDrift, ...]:
        drifts = []
        for item in expected:
            current = self._hash_optional(item.path)
            if current != item.sha256:
                drifts.append(TaskSourceDrift(item.path, item.sha256, current))
        return tuple(drifts)

    def _hash_required(self, relative_path: str) -> str:
        target = self._resolver.resolve(relative_path)
        if not target.is_file():
            raise WorkspaceAccessError(f"Task kaynak yolu dosya değil: {relative_path}")
        if target.stat().st_size > self._max_file_bytes:
            raise WorkspaceAccessError(f"Task kaynak dosyası boyut sınırını aşıyor: {relative_path}")
        return hashlib.sha256(target.read_bytes()).hexdigest()

    def _hash_optional(self, relative_path: str) -> str | None:
        try:
            return self._hash_required(relative_path)
        except (OSError, WorkspaceAccessError):
            return None
