import re

from boru.database_tools.models import DatabaseAction, DatabaseRequest


class RuleBasedDatabaseRequestParser:
    _PATTERNS = (
        (DatabaseAction.TABLES, re.compile(r"^veritabanı\s+tabloları\s*:\s*(.+)$", re.I)),
        (DatabaseAction.SCHEMA, re.compile(r"^veritabanı\s+şema(?:sı)?\s*:\s*(.+)$", re.I)),
        (DatabaseAction.DESCRIBE, re.compile(r"^veritabanı\s+tablo\s+açıkla\s*:\s*(.+)$", re.I)),
        (DatabaseAction.QUERY, re.compile(r"^veritabanı\s+sorgula\s*:\s*(.+)$", re.I | re.S)),
    )

    def parse(self, user_message: str) -> DatabaseRequest | None:
        text = user_message.strip()
        for action, pattern in self._PATTERNS:
            match = pattern.fullmatch(text)
            if not match:
                continue
            payload = match.group(1).strip()
            if action in {DatabaseAction.DESCRIBE, DatabaseAction.QUERY}:
                path, separator, value = payload.partition("|")
                if not separator or not path.strip() or not value.strip():
                    raise ValueError("Bu işlem için 'veritabanı yolu | değer' biçimini kullanın.")
                return DatabaseRequest(action, path.strip(), value.strip())
            return DatabaseRequest(action, payload)
        return None

    @staticmethod
    def is_database_intent(user_message: str) -> bool:
        return re.match(r"^\s*veritabanı\s+", user_message, re.IGNORECASE) is not None
