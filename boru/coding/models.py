from dataclasses import dataclass

from boru.architecture.models import ArchitecturePlan, ArchitectureRequest
from boru.tools.project_edit_models import ProjectEditProposal


@dataclass(frozen=True, slots=True)
class CodingRequest:
    architecture_request: ArchitectureRequest

    @property
    def task(self) -> str:
        return self.architecture_request.task


@dataclass(frozen=True, slots=True)
class CodingSession:
    request: CodingRequest
    architecture_plan: ArchitecturePlan
    proposal: ProjectEditProposal
