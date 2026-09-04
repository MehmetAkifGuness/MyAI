import re

from boru.tools.write_models import (
    WriteRequest,
)


class RuleBasedWriteIntentDetector:
    """Dosya oluşturma/yazma/değiştirme niyeti taşıyan mesajları seçer."""

    _PATTERNS = (
        re.compile(
            r"\b(?:dosya|dosyayı|dosyası|dosyasını|dosyasına)\b"
            r".*\b(?:oluştur|yaz|değiştir|düzenle|güncelle)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(?:^|\s)[\w./\\-]+\."
            r"(?:py|json|txt|md|yaml|yml|toml|ini|cfg|csv|xml|html|css|js|ts|dart|java|cs|sql)"
            r".*\b(?:oluştur|yaz|değiştir|düzenle|güncelle)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    )

    def is_write_intent(
        self,
        user_message: str,
    ) -> bool:
        text = user_message.strip()

        if not text:
            return False

        return any(
            pattern.search(text)
            is not None
            for pattern in self._PATTERNS
        )


class RuleBasedWriteRequestParser:
    """Tam içerik verilen kontrollü create-file isteklerini ayrıştırır."""

    _PATTERNS = (
        re.compile(
            r"^\s*dosya\s+oluştur\s*:\s*"
            r"(?P<path>[^\r\n]+)"
            r"\r?\n\s*içerik\s*:\s*"
            r"\r?\n?(?P<content>.*)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*(?P<path>[^\r\n:]+?)\s+"
            r"dosyasını\s+şu\s+içerikle\s+oluştur\s*:\s*"
            r"\r?\n?(?P<content>.*)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*(?P<path>[^\r\n:]+?)\s+"
            r"dosyasına\s+şunu\s+yaz\s*:\s*"
            r"\r?\n?(?P<content>.*)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*(?P<path>[^\r\n:]+?)\s+"
            r"dosyasını\s+oluştur\s+ve\s+içine\s+şunu\s+yaz\s*:\s*"
            r"\r?\n?(?P<content>.*)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*(?P<path>[^\r\n:]+?)\s+"
            r"dosyasını\s+oluştur\s*:\s*"
            r"\r?\n?(?P<content>.*)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
    )

    def parse(
        self,
        user_message: str,
    ) -> WriteRequest | None:
        for pattern in self._PATTERNS:
            match = pattern.fullmatch(
                user_message
            )

            if match is None:
                continue

            path = (
                match.group("path")
                .strip()
                .strip("\"'")
            )

            content = match.group(
                "content"
            )

            return WriteRequest(
                path=path,
                content=content,
            )

        return None