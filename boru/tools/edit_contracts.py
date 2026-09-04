from typing import Protocol

from boru.tools.edit_models import (
    EditOutcome,
    EditProposal,
    EditRequest,
    EditSource,
    SmartEditRequest,
)


class EditRequestParser(Protocol):
    def parse(
        self,
        user_message: str,
    ) -> EditRequest | None:
        ...


class SmartEditRequestParser(Protocol):
    def parse(
        self,
        user_message: str,
    ) -> SmartEditRequest | None:
        ...


class EditProposalPreparer(Protocol):
    def prepare_exact_replacement(
        self,
        request: EditRequest,
    ) -> EditProposal:
        ...


class SmartEditProposalPreparer(Protocol):
    def prepare_smart_edit(
        self,
        request: SmartEditRequest,
    ) -> EditProposal:
        ...


class SmartEditWorkspace(Protocol):
    def read_edit_source(
        self,
        relative_path: str,
    ) -> EditSource:
        ...

    def prepare_exact_replacement(
        self,
        request: EditRequest,
        *,
        expected_sha256: str | None = None,
    ) -> EditProposal:
        ...


class WorkspaceEditor(Protocol):
    def apply_text_update(
        self,
        *,
        relative_path: str,
        content: str,
        expected_sha256: str,
    ) -> EditOutcome:
        ...