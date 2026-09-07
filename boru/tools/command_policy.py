import re
import subprocess
import sys

from boru.tools.command_models import (
    CommandKind,
    CommandRequest,
    CommandRisk,
    CommandSpec,
)


class SafeCommandPolicy:
    """Kullanıcı metnini yalnızca sabit, izinli komut planlarına dönüştürür."""

    _SAFE_TARGET = re.compile(r"^[A-Za-z0-9_./\\-]+$")

    def build(self, request: CommandRequest) -> CommandSpec:
        self._validate_target(request.target)
        self._validate_target(request.working_directory)
        if request.kind in {CommandKind.PIP_CHECK, CommandKind.ENVIRONMENT} and request.target:
            raise ValueError("Bu komut hedef kabul etmez.")
        arguments = self._arguments_for(request)
        display = subprocess.list2cmdline((sys.executable, *arguments))
        return CommandSpec(
            kind=request.kind,
            executable=sys.executable,
            arguments=arguments,
            display=display,
            risk=CommandRisk.SAFE,
            working_directory=request.working_directory,
        )

    @staticmethod
    def _arguments_for(request: CommandRequest) -> tuple[str, ...]:
        target = request.target

        if request.kind is CommandKind.UNITTEST:
            if target:
                return ("-m", "unittest", target)
            return (
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
            )

        targeted = {
            CommandKind.PYTEST: ("-m", "pytest", target or "tests"),
            CommandKind.RUFF: ("-m", "ruff", "check", target or "."),
            CommandKind.MYPY: ("-m", "mypy", target or "boru"),
            CommandKind.COMPILEALL: ("-m", "compileall", "-q", target or "."),
        }
        if request.kind in targeted:
            return targeted[request.kind]

        fixed = {
            CommandKind.PIP_CHECK: ("-m", "pip", "check"),
            CommandKind.ENVIRONMENT: (
                "-c",
                "import os,platform,sys;"
                "print('python=' + platform.python_version());"
                "print('platform=' + platform.system().lower());"
                "print('cwd=' + os.getcwd());"
                "print('executable=' + sys.executable)",
            ),
        }
        if request.kind in fixed:
            return fixed[request.kind]

        raise ValueError("Desteklenmeyen komut türü.")

    @classmethod
    def _validate_target(cls, target: str) -> None:
        if not target:
            return

        normalized = target.replace("\\", "/")
        if (
            cls._SAFE_TARGET.fullmatch(target) is None
            or normalized.startswith("/")
            or ":" in normalized
            or ".." in normalized.split("/")
        ):
            raise ValueError("Komut hedefi güvenli bir göreli yol veya modül olmalıdır.")
