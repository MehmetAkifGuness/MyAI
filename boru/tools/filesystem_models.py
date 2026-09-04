from dataclasses import dataclass
from enum import Enum


class FilesystemOperation(str, Enum):
    DELETE_FILE = "delete_file"
    MOVE_FILE = "move_file"
    RENAME_FILE = "rename_file"
    MAKE_DIRECTORY = "make_directory"


@dataclass(frozen=True, slots=True)
class FilesystemOperationRequest:
    operation: FilesystemOperation
    source_path: str
    destination_path: str | None = None

    def __post_init__(self) -> None:
        source = self.source_path.strip().strip("\"'")
        destination = (
            self.destination_path.strip().strip("\"'")
            if self.destination_path is not None
            else None
        )

        if not source:
            raise ValueError("Dosya sistemi işlem yolu boş olamaz.")

        needs_destination = self.operation in {
            FilesystemOperation.MOVE_FILE,
            FilesystemOperation.RENAME_FILE,
        }

        if needs_destination and not destination:
            raise ValueError("Taşıma/yeniden adlandırma hedefi boş olamaz.")

        if not needs_destination and destination is not None:
            raise ValueError("Bu dosya sistemi işlemi hedef yol kabul etmez.")

        if destination == source:
            raise ValueError("Kaynak ve hedef yol aynı olamaz.")

        object.__setattr__(self, "source_path", source)
        object.__setattr__(self, "destination_path", destination)


@dataclass(frozen=True, slots=True)
class FilesystemOperationProposal:
    request: FilesystemOperationRequest
    expected_source_sha256: str | None = None
    source_byte_count: int = 0

    def __post_init__(self) -> None:
        if self.source_byte_count < 0:
            raise ValueError("Kaynak byte sayısı negatif olamaz.")

        if (
            self.request.operation
            is not FilesystemOperation.MAKE_DIRECTORY
            and not self.expected_source_sha256
        ):
            raise ValueError("Dosya işlemi için kaynak hash'i gereklidir.")


@dataclass(frozen=True, slots=True)
class FilesystemOperationOutcome:
    operation: FilesystemOperation
    source_path: str
    destination_path: str | None = None

