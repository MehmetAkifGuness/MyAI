from typing import Protocol


class ProjectMemoryRepository(Protocol):
    def load(self) -> dict[str, str]:
        ...

    def save(self, entries: dict[str, str]) -> None:
        ...


class ProjectMemoryServicePort(Protocol):
    def list_entries(self) -> tuple[tuple[str, str], ...]:
        ...

    def save_entry(self, key: str, value: str) -> str:
        ...

    def delete_entry(self, key: str) -> bool:
        ...

    def build_context(self) -> str:
        ...
