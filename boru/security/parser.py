import re

from boru.security.models import SecurityScanRequest


class RuleBasedSecurityRequestParser:
    _PATTERN = re.compile(
        r"^\s*(?:güvenlik\s+tara|security\s+agent|security)\s*:\s*"
        r"(?P<paths>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _INTENT = re.compile(
        r"^\s*(?:güvenlik\s+tara|security\s+agent|security)\b",
        re.IGNORECASE,
    )

    def __init__(self, max_paths: int = 8) -> None:
        if max_paths < 1:
            raise ValueError("Security Agent dosya sınırı pozitif olmalıdır.")
        self._max_paths = max_paths

    def parse(self, user_message: str) -> SecurityScanRequest | None:
        match = self._PATTERN.fullmatch(user_message)
        if match is None:
            return None
        paths = tuple(
            path.strip().strip("`\"'")
            for path in match.group("paths").split(",")
            if path.strip()
        )
        if len(paths) > self._max_paths:
            raise ValueError(f"En fazla {self._max_paths} kaynak dosya belirtilebilir.")
        return SecurityScanRequest(paths)

    def is_security_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None

