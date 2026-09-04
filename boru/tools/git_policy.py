import shutil
import subprocess
from pathlib import Path

from boru.tools.command_models import (
    CommandKind,
    CommandRequest,
    CommandRisk,
    CommandSpec,
)
from boru.tools.git_parser import RuleBasedGitRequestParser


class GitCommandPolicy:
    _READ_ARGUMENTS = {
        CommandKind.GIT_STATUS: ("status", "--short", "--branch"),
        CommandKind.GIT_DIFF: ("diff", "--"),
        CommandKind.GIT_BRANCH: ("branch", "--list"),
        CommandKind.GIT_LOG: ("log", "-n", "20", "--oneline", "--decorate"),
    }

    def __init__(self, git_executable: str | None = None) -> None:
        executable = git_executable or shutil.which("git")
        if executable is None:
            raise ValueError("Git executable bulunamadı.")
        resolved = Path(executable).resolve()
        if not resolved.is_file():
            raise ValueError("Git executable geçerli bir dosya değil.")
        self._executable = str(resolved)

    def build(self, request: CommandRequest) -> CommandSpec:
        if request.kind in self._READ_ARGUMENTS:
            arguments = self._READ_ARGUMENTS[request.kind]
            risk = CommandRisk.SAFE
        elif request.kind is CommandKind.GIT_ADD:
            RuleBasedGitRequestParser.validate_path(request.target)
            arguments = ("add", "--", request.target)
            risk = CommandRisk.REQUIRES_APPROVAL
        elif request.kind is CommandKind.GIT_COMMIT:
            RuleBasedGitRequestParser.validate_commit_message(request.target)
            arguments = ("commit", "-m", request.target)
            risk = CommandRisk.REQUIRES_APPROVAL
        elif request.kind is CommandKind.GIT_RESTORE:
            RuleBasedGitRequestParser.validate_path(request.target)
            arguments = ("restore", "--", request.target)
            risk = CommandRisk.REQUIRES_APPROVAL
        else:
            raise ValueError("Desteklenmeyen Git işlemi.")

        return CommandSpec(
            kind=request.kind,
            executable=self._executable,
            arguments=arguments,
            display=subprocess.list2cmdline(("git", *arguments)),
            risk=risk,
        )
