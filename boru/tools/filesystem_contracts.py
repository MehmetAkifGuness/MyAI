from typing import Protocol

from boru.tools.filesystem_models import (
    FilesystemOperationOutcome,
    FilesystemOperationProposal,
    FilesystemOperationRequest,
)


class FilesystemOperationRequestParser(Protocol):
    def parse(
        self,
        user_message: str,
    ) -> FilesystemOperationRequest | None:
        ...

    def is_operation_intent(
        self,
        user_message: str,
    ) -> bool:
        ...


class FilesystemOperationWorkspace(Protocol):
    def prepare(
        self,
        request: FilesystemOperationRequest,
    ) -> FilesystemOperationProposal:
        ...

    def apply(
        self,
        proposal: FilesystemOperationProposal,
    ) -> FilesystemOperationOutcome:
        ...
