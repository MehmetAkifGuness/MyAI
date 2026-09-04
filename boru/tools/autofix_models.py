from dataclasses import dataclass

from boru.tools.command_models import CommandSpec
from boru.tools.project_edit_models import ProjectEditProposal


@dataclass(slots=True)
class AutoFixSession:
    command: CommandSpec
    applied_attempts: int = 0
    proposal: ProjectEditProposal | None = None
