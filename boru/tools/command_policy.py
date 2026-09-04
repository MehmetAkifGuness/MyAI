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
        arguments = self._arguments_for(request)
        display = subprocess.list2cmdline((sys.executable, *arguments))
        return CommandSpec(
            kind=request.kind,
            executable=sys.executable,
            arguments=arguments,
            display=display,
            risk=CommandRisk.SAFE,
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

        if request.kind is CommandKind.PYTEST:
            return ("-m", "pytest", target or "tests")

        if request.kind is CommandKind.RUFF:
            return ("-m", "ruff", "check", target or ".")

        if request.kind is CommandKind.MYPY:
            return ("-m", "mypy", target or "boru")

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
