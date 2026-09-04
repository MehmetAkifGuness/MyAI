import re

from boru.tools.filesystem_models import (
    FilesystemOperation,
    FilesystemOperationRequest,
)


class RuleBasedFilesystemOperationParser:
    """Açık ve sınırlandırılmış DELETE, MOVE, RENAME ve MKDIR komutlarını ayrıştırır."""

    _DELETE_PATTERNS = (
        re.compile(r"^\s*dosya\s+sil\s*:\s*(?P<source>.+?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*(?P<source>.+?)\s+dosyasını\s+sil\s*[.!]?\s*$", re.IGNORECASE),
    )
    _MOVE_PATTERNS = (
        re.compile(
            r"^\s*dosya\s+taşı\s*:\s*(?P<source>.+?)\s*->\s*(?P<destination>.+?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<source>.+?)\s+dosyasını\s+(?P<destination>.+?)\s+konumuna\s+taşı\s*[.!]?\s*$",
            re.IGNORECASE,
        ),
    )
    _RENAME_PATTERNS = (
        re.compile(
            r"^\s*dosya\s+yeniden\s+adlandır\s*:\s*(?P<source>.+?)\s*->\s*(?P<destination>.+?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<source>.+?)\s+dosyasını\s+(?P<destination>.+?)\s+olarak\s+yeniden\s+adlandır\s*[.!]?\s*$",
            re.IGNORECASE,
        ),
    )
    _MKDIR_PATTERNS = (
        re.compile(r"^\s*klasör\s+oluştur\s*:\s*(?P<source>.+?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*(?P<source>.+?)\s+klasörünü\s+oluştur\s*[.!]?\s*$", re.IGNORECASE),
    )
    _INTENT_PATTERN = re.compile(
        r"(?:\b(?:dosya|dosyayı|dosyasını)\b.*\b(?:sil|taşı|yeniden\s+adlandır)\b|"
        r"\b(?:klasör|klasörünü)\b.*\boluştur\b)",
        re.IGNORECASE | re.DOTALL,
    )

    def parse(
        self,
        user_message: str,
    ) -> FilesystemOperationRequest | None:
        mappings = (
            (FilesystemOperation.DELETE_FILE, self._DELETE_PATTERNS),
            (FilesystemOperation.MOVE_FILE, self._MOVE_PATTERNS),
            (FilesystemOperation.RENAME_FILE, self._RENAME_PATTERNS),
            (FilesystemOperation.MAKE_DIRECTORY, self._MKDIR_PATTERNS),
        )

        for operation, patterns in mappings:
            for pattern in patterns:
                match = pattern.fullmatch(user_message)
                if match is None:
                    continue

                groups = match.groupdict()
                return FilesystemOperationRequest(
                    operation=operation,
                    source_path=groups["source"],
                    destination_path=groups.get("destination"),
                )

        return None

    def is_operation_intent(
        self,
        user_message: str,
    ) -> bool:
        return self._INTENT_PATTERN.search(
            user_message
        ) is not None
