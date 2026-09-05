from collections.abc import Sequence
from pathlib import Path
from threading import RLock

from boru.knowledge.models import KnowledgeDocument
from boru.persistence import AtomicJsonFileStore, JsonFileReadError, JsonFileWriteError


class JsonKnowledgeRepository:
    _VERSION = 1

    def __init__(self, file_path: str | Path):
        self._store = AtomicJsonFileStore(file_path)
        self._lock = RLock()

    def load_all(self) -> list[KnowledgeDocument]:
        with self._lock:
            try:
                data = self._store.read()
            except JsonFileReadError as error:
                raise RuntimeError(f"Bilgi indeksi okunamadı: {self._store.path}") from error

            if data is None:
                return []
            if not isinstance(data, dict) or data.get("version") != self._VERSION:
                raise RuntimeError("Bilgi indeksi geçerli bir V1 JSON nesnesi değil.")
            raw_documents = data.get("documents")
            if not isinstance(raw_documents, list):
                raise RuntimeError("Bilgi indeksi belge listesi içermiyor.")

            try:
                return [KnowledgeDocument.from_dict(item) for item in raw_documents]
            except (TypeError, ValueError) as error:
                raise RuntimeError("Bilgi indeksinde geçersiz belge bulundu.") from error

    def save_all(self, documents: Sequence[KnowledgeDocument]) -> None:
        with self._lock:
            try:
                self._store.write(
                    {
                        "version": self._VERSION,
                        "documents": [
                            document.to_dict()
                            for document in sorted(
                                documents,
                                key=lambda item: item.source_path.casefold(),
                            )
                        ],
                    }
                )
            except JsonFileWriteError as error:
                raise RuntimeError(f"Bilgi indeksi yazılamadı: {self._store.path}") from error
