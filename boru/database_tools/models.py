from dataclasses import dataclass
from enum import Enum


class DatabaseAction(str, Enum):
    TABLES = "tables"
    SCHEMA = "schema"
    DESCRIBE = "describe"
    QUERY = "query"


@dataclass(frozen=True, slots=True)
class DatabaseRequest:
    action: DatabaseAction
    database_path: str
    value: str = ""


@dataclass(frozen=True, slots=True)
class DatabaseResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    truncated: bool = False
