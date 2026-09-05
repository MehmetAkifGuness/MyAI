import re
from pathlib import PurePosixPath

from boru.tools.workspace import ReadOnlyWorkspace


class SafeKnowledgeDocumentLoader:
    _ALLOWED_SUFFIXES = frozenset(
        {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv"}
    )
    _SECRET_PATTERNS = (
        re.compile(r"\bsk-(?:live-|proj-)?[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )

    def __init__(self, workspace: ReadOnlyWorkspace):
        self._workspace = workspace

    def load(self, relative_path: str) -> tuple[str, str]:
        normalized = relative_path.strip().replace("\\", "/")
        suffix = PurePosixPath(normalized).suffix.casefold()
        if suffix not in self._ALLOWED_SUFFIXES:
            raise ValueError(
                "Bilgi kaynağı yalnızca md, txt, rst, json, yaml, yml, toml veya csv olabilir."
            )

        content = self._workspace.read_text_file(normalized)
        if not content.strip():
            raise ValueError("Boş belge bilgi kaynağı olarak eklenemez.")
        if any(pattern.search(content) for pattern in self._SECRET_PATTERNS):
            raise ValueError("Belge secret veya erişim anahtarı benzeri hassas veri içeriyor.")
        return normalized, content
