from typing import Protocol

from boru.tools.edit_models import (
    EditOutcome,
    EditProposal,
    EditRequest,
)


class EditRequestParser(Protocol):
    def parse(
        self,
        user_message: str,
    ) -> EditRequest | None:
        ...


class EditProposalPreparer(Protocol):
    def prepare_exact_replacement(
        self,
        request: EditRequest,
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