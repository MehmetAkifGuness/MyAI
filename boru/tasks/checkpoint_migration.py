from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskCheckpointMigration:
    document: dict[str, object]
    migrated_from: int | None = None

    @property
    def migrated(self) -> bool:
        return self.migrated_from is not None


class TaskCheckpointMigrator:
    """Upgrade known checkpoint documents without mutating the source object."""

    SCHEMA = "boru.task-checkpoint"
    CURRENT_VERSION = 2
    _V1_FIELDS = frozenset({"version", "plan", "journal", "fingerprints"})
    _V2_FIELDS = frozenset(
        {"schema", "version", "plan", "journal", "fingerprints"}
    )

    def migrate(self, data: object) -> TaskCheckpointMigration:
        if not isinstance(data, dict):
            raise TypeError("Checkpoint kökü nesne olmalıdır.")
        version = data.get("version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("Checkpoint sürümü geçersiz.")
        if version == 1:
            return TaskCheckpointMigration(self._from_v1(data), migrated_from=1)
        if version != self.CURRENT_VERSION:
            raise ValueError(f"Desteklenmeyen checkpoint sürümü: {version}")
        self._require_fields(data, self._V2_FIELDS)
        if data.get("schema") != self.SCHEMA:
            raise ValueError("Checkpoint şema kimliği geçersiz.")
        return TaskCheckpointMigration(deepcopy(data))

    def _from_v1(self, data: dict[str, object]) -> dict[str, object]:
        self._require_fields(data, self._V1_FIELDS)
        return {
            "schema": self.SCHEMA,
            "version": self.CURRENT_VERSION,
            "plan": deepcopy(data.get("plan")),
            "journal": deepcopy(data.get("journal")),
            "fingerprints": deepcopy(data.get("fingerprints", [])),
        }

    @staticmethod
    def _require_fields(data: dict[str, object], allowed: frozenset[str]) -> None:
        required = {"version", "plan", "journal"}
        missing = required - data.keys()
        unexpected = data.keys() - allowed
        if missing:
            raise ValueError(
                "Checkpoint zorunlu alanları eksik: " + ", ".join(sorted(missing))
            )
        if unexpected:
            raise ValueError(
                "Checkpoint beklenmeyen alan içeriyor: "
                + ", ".join(sorted(unexpected))
            )
