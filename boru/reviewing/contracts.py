from typing import Protocol

from boru.reviewing.models import CodeReviewReport


class CodeReviewScanner(Protocol):
    def scan(self, paths: tuple[str, ...]) -> CodeReviewReport:
        ...


class CodeReviewer(Protocol):
    def review_paths(self, paths: tuple[str, ...]) -> str:
        ...

