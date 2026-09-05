import re

from boru.knowledge.models import KnowledgeAction, KnowledgeRequest


class RuleBasedKnowledgeRequestParser:
    _VALUE_PATTERNS = (
        (KnowledgeAction.ADD, re.compile(r"^(?:bilgi\s+kaynağı\s+ekle|bilgi\s+indeksle)\s*:\s*(.+)$", re.I)),
        (KnowledgeAction.DELETE, re.compile(r"^bilgi\s+kaynağı\s+sil\s*:\s*(.+)$", re.I)),
        (KnowledgeAction.SEARCH, re.compile(r"^bilgi\s+ara\s*:\s*(.+)$", re.I | re.S)),
        (KnowledgeAction.ASK, re.compile(r"^bilgiye\s+göre\s+sor\s*:\s*(.+)$", re.I | re.S)),
    )
    _LIST_PATTERN = re.compile(r"^bilgi\s+kaynak(?:ları|larını\s+listele)$", re.I)

    def parse(self, user_message: str) -> KnowledgeRequest | None:
        text = user_message.strip()
        if not text:
            return None
        if self._LIST_PATTERN.fullmatch(" ".join(text.split())):
            return KnowledgeRequest(KnowledgeAction.LIST)
        for action, pattern in self._VALUE_PATTERNS:
            match = pattern.fullmatch(text)
            if match:
                return KnowledgeRequest(action, match.group(1).strip())
        return None
