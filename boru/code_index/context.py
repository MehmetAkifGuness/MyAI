import re
from collections.abc import Sequence


class RelevantFileRanker:
    """Ranks a safe manifest using task text and bounded code-index evidence."""

    _TERMS = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]{2,}")
    _STOP = {"the", "and", "for", "with", "için", "olan", "yalnızca", "dosya", "yap"}

    def __init__(self, code_index, *, max_candidates: int = 40):
        if max_candidates < 4 or max_candidates > 100:
            raise ValueError("Bağlam aday sınırı 4-100 olmalıdır.")
        self._index = code_index
        self._max_candidates = max_candidates

    def rank(self, instruction: str, available_paths: Sequence[str]) -> tuple[str, ...]:
        catalog = tuple(dict.fromkeys(path.strip() for path in available_paths if path.strip()))
        folded = instruction.casefold().replace("\\", "/")
        terms = tuple(dict.fromkeys(
            term.casefold() for term in self._TERMS.findall(instruction)
            if term.casefold() not in self._STOP
        ))[:24]
        scores = {path: 0 for path in catalog}
        for path in catalog:
            normalized = path.casefold().replace("\\", "/")
            if normalized in folded:
                scores[path] += 1000
            scores[path] += 25 * sum(term in normalized for term in terms)
        try:
            hits = self._index.search(" ".join(terms), max_results=30) if terms else ()
        except (OSError, ValueError):
            hits = ()
        for position, hit in enumerate(hits):
            if hit.path in scores:
                scores[hit.path] += max(1, 100 - position)
        ranked = [path for path in catalog if scores[path] > 0]
        if not ranked:
            return catalog
        ranked.sort(key=lambda path: (-scores[path], path.casefold()))
        selected = ranked[: self._max_candidates]
        # Keep sibling source/test files available when one side ranked.
        stems = {self._stem(path) for path in selected}
        siblings = [path for path in catalog if self._stem(path) in stems and path not in selected]
        return tuple((selected + siblings)[: self._max_candidates])

    @staticmethod
    def _stem(path: str) -> str:
        normalized = path.casefold().replace("\\", "/")
        leaf = normalized.rsplit("/", 1)[-1].removesuffix(".py")
        return leaf.removeprefix("test_").removesuffix("_test")
