from dataclasses import dataclass
from enum import Enum


class CodeSymbolKind(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    ASSIGNMENT = "assignment"


@dataclass(frozen=True, slots=True)
class CodeSymbol:
    path: str
    name: str
    qualified_name: str
    kind: CodeSymbolKind
    line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class CodeSearchHit:
    path: str
    line: int
    preview: str
    score: int
    symbol: str | None = None


@dataclass(frozen=True, slots=True)
class CodeIndexSummary:
    file_count: int
    symbol_count: int
    suffix_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class RelatedCodeFile:
    path: str
    score: int
    imported_via: str
    matched_calls: tuple[str, ...] = ()
