import hashlib
from collections.abc import Sequence
from pathlib import PurePosixPath
from threading import RLock

from boru.knowledge.contracts import (
    KnowledgeDocumentLoader,
    KnowledgeRepository,
    KnowledgeRetriever,
)
from boru.knowledge.models import KnowledgeDocument, KnowledgeHit


class KnowledgeService:
    _MAX_DOCUMENTS = 64
    _MAX_CHUNKS = 2048

    def __init__(self, repository, loader, chunker, retriever):
        self._repository: KnowledgeRepository = repository
        self._loader: KnowledgeDocumentLoader = loader
        self._chunker = chunker
        self._retriever: KnowledgeRetriever = retriever
        self._lock = RLock()
        self._documents = self._load_documents()

    def add_source(self, relative_path: str) -> str:
        source_path, content = self._loader.load(relative_path)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunks = self._chunker.split(source_path, content)
        if not chunks:
            raise ValueError("Belgeden aranabilir bilgi parçası üretilemedi.")

        document = KnowledgeDocument(source_path, digest, chunks)
        with self._lock:
            previous = self._documents.get(source_path)
            if previous is not None and previous.content_sha256 == digest:
                return "unchanged"
            if previous is None and len(self._documents) >= self._MAX_DOCUMENTS:
                raise ValueError("Bilgi indeksi belge sınırına ulaştı.")
            new_chunk_total = sum(
                len(item.chunks)
                for path, item in self._documents.items()
                if path != source_path
            ) + len(chunks)
            if new_chunk_total > self._MAX_CHUNKS:
                raise ValueError("Bilgi indeksi parça sınırına ulaştı.")

            self._documents[source_path] = document
            try:
                self._persist()
            except RuntimeError:
                if previous is None:
                    del self._documents[source_path]
                else:
                    self._documents[source_path] = previous
                raise
            return "created" if previous is None else "updated"

    def delete_source(self, relative_path: str) -> bool:
        source_path = relative_path.strip().replace("\\", "/")
        with self._lock:
            previous = self._documents.pop(source_path, None)
            if previous is None:
                return False
            try:
                self._persist()
            except RuntimeError:
                self._documents[source_path] = previous
                raise
            return True

    def list_sources(self) -> tuple[tuple[str, int], ...]:
        with self._lock:
            return tuple(
                (document.source_path, len(document.chunks))
                for document in sorted(
                    self._documents.values(), key=lambda item: item.source_path.casefold()
                )
            )

    def search(self, query: str, limit: int = 5) -> list[KnowledgeHit]:
        with self._lock:
            documents: Sequence[KnowledgeDocument] = tuple(self._documents.values())
        return self._retriever.retrieve(query, documents, limit)

    def _persist(self) -> None:
        self._repository.save_all(tuple(self._documents.values()))

    def _load_documents(self) -> dict[str, KnowledgeDocument]:
        documents = self._repository.load_all()
        if len(documents) > self._MAX_DOCUMENTS:
            raise RuntimeError("Bilgi indeksi belge sınırını aşıyor.")
        if sum(len(document.chunks) for document in documents) > self._MAX_CHUNKS:
            raise RuntimeError("Bilgi indeksi parça sınırını aşıyor.")

        loaded: dict[str, KnowledgeDocument] = {}
        for document in documents:
            path = PurePosixPath(document.source_path)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in document.source_path
                or any(character in document.source_path for character in "\r\n\0")
            ):
                raise RuntimeError("Bilgi indeksinde güvenli olmayan kaynak yolu bulundu.")
            if document.source_path in loaded:
                raise RuntimeError("Bilgi indeksinde yinelenen kaynak bulundu.")
            loaded[document.source_path] = document
        return loaded
