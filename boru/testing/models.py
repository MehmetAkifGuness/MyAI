from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TestAgentRequest:
    source_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized = tuple(
            path.strip().replace("\\", "/")
            for path in self.source_paths
            if path.strip()
        )
        if not normalized:
            raise ValueError("En az bir kaynak dosya belirtilmelidir.")
        if len(set(path.casefold() for path in normalized)) != len(normalized):
            raise ValueError("Aynı kaynak dosya birden fazla kez belirtilemez.")
        object.__setattr__(self, "source_paths", normalized)


@dataclass(frozen=True, slots=True)
class RelatedTestSelection:
    source_paths: tuple[str, ...]
    test_paths: tuple[str, ...]

