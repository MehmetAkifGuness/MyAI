from typing import Protocol

from boru.testing.models import RelatedTestSelection


class RelatedTestDiscoverer(Protocol):
    def discover(self, source_paths: tuple[str, ...]) -> RelatedTestSelection:
        ...


class RegressionTestRunner(Protocol):
    def run_for_paths(self, source_paths: tuple[str, ...]) -> str:
        ...

