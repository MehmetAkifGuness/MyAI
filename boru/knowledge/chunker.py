import hashlib

from boru.knowledge.models import KnowledgeChunk


class TextKnowledgeChunker:
    def __init__(self, max_characters: int = 1200, overlap_characters: int = 150):
        if max_characters < 100:
            raise ValueError("max_characters en az 100 olmalıdır.")
        if overlap_characters < 0 or overlap_characters >= max_characters:
            raise ValueError("overlap_characters parça boyutundan küçük olmalıdır.")
        self._max_characters = max_characters
        self._overlap_characters = overlap_characters

    def split(self, source_path: str, content: str) -> tuple[KnowledgeChunk, ...]:
        chunks: list[KnowledgeChunk] = []
        start = 0
        length = len(content)

        while start < length:
            end = min(start + self._max_characters, length)
            if end < length:
                boundary = max(content.rfind("\n", start, end), content.rfind(" ", start, end))
                if boundary > start + self._max_characters // 2:
                    end = boundary

            raw_text = content[start:end]
            text = raw_text.strip()
            if text:
                content_start = start + len(raw_text) - len(raw_text.lstrip())
                content_end = content_start + len(text)
                line_start = content.count("\n", 0, content_start) + 1
                line_end = line_start + content.count("\n", content_start, content_end)
                digest = hashlib.sha256(
                    f"{source_path}\0{start}\0{text}".encode("utf-8")
                ).hexdigest()
                chunks.append(KnowledgeChunk(digest, text, line_start, line_end))

            if end >= length:
                break
            start = max(start + 1, end - self._overlap_characters)

        return tuple(chunks)
