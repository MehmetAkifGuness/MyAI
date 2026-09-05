from typing import Protocol

from boru.security.models import SecurityScanReport


class SecurityScanner(Protocol):
    def scan(self, paths: tuple[str, ...]) -> SecurityScanReport:
        ...


class SecurityReviewer(Protocol):
    def review_paths(self, paths: tuple[str, ...]) -> str:
        ...

