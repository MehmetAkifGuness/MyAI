import os
from pathlib import Path


class CheckpointLease:
    """An OS-held project lease; process exit releases it even after a crash."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError("Checkpoint kilidi sembolik bağlantı olamaz.")
        self._handle = path.open("a+b")
        try:
            self._handle.seek(0, os.SEEK_END)
            if self._handle.tell() == 0:
                self._handle.write(b"0")
                self._handle.flush()
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._handle.close()
            raise RuntimeError("[PROJECT_LOCKED] Bu projeyi başka bir Börü oturumu kullanıyor.") from error

    def close(self):
        self._handle.close()

    def __del__(self):
        handle = getattr(self, "_handle", None)
        if handle is not None:
            handle.close()
