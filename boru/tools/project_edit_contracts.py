from collections.abc import Sequence
from typing import Protocol

from boru.tools.project_edit_models import (
    ProjectEditOutcome,
    ProjectEditProposal,
    ProjectEditRequest,
    ProjectFileSelection,
)


class ProjectEditRequestParser(Protocol):
    def parse(
        self,
        user_message: str,
    ) -> ProjectEditRequest | None:
        ...


class ProjectFileIndexer(Protocol):
    def list_editable_files(
        self,
    ) -> tuple[str, ...]:
        ...


class ProjectFileSelector(Protocol):
    def select_files(
        self,
        *,
        request: ProjectEditRequest,
        available_paths: Sequence[str],
    ) -> ProjectFileSelection:
        ...


class ProjectEditProposalPreparer(Protocol):
    def prepare_project_edit(
        self,
        request: ProjectEditRequest,
    ) -> ProjectEditProposal:
        ...


class ProjectEditApplier(Protocol):
    def apply_project_edit(
        self,
        proposal: ProjectEditProposal,
    ) -> ProjectEditOutcome:
        ...