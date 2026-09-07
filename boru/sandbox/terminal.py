import re

from boru.tools.command_models import CommandKind, CommandRequest
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.test_results import TestOutputParser
from boru.tools.workspace import WorkspacePathResolver


class SandboxTerminalCoordinator:
    """Small CLI grammar mapped to canonical sandbox commands, never a shell."""

    _COMMAND = re.compile(
        r"^(?:python\s+-m\s+)?(unittest|pytest|ruff|mypy)"
        r"(?:\s+(.*))?$", re.IGNORECASE,
    )
    _USAGE = (
        "İzinli terminal komutları: unittest [hedef], pytest [hedef], "
        "ruff check [hedef], mypy [hedef]. Örnek: terminal: python -m unittest tests/test_v3000.py"
    )

    def __init__(self, root, executor):
        self._resolver = WorkspacePathResolver(root)
        self._executor = executor

    @property
    def has_pending(self):
        return False

    def resolve(self, message):
        normalized = " ".join(message.strip().casefold().split())
        if normalized in {"terminal durumu", "terminal ortamı"}:
            return (
                "TERMİNAL ORTAMI\nÇalışma dizini: /workspace (proje kopyası)\n"
                "Yürütme: Docker Linux; Python modülleri; shell kapalı.\n"
                + self._executor.status() + "\n" + self._USAGE
            )
        if not normalized.startswith("terminal"):
            return None
        prefix, separator, command = message.partition(":")
        if not separator or prefix.strip().casefold() != "terminal":
            return self._USAGE
        try:
            spec = self._parse(command.strip())
            result = self._executor.execute(spec)
        except (OSError, RuntimeError, ValueError) as error:
            return f"TERMİNAL RAPORU\nDurum: ÇALIŞTIRILAMADI\n{error}"
        return self._render(spec, result)

    @staticmethod
    def _render(spec, result):
        summary = TestOutputParser().parse(result)
        status = "BAŞARILI" if result.succeeded else "BAŞARISIZ"
        if result.timed_out:
            status = "ZAMAN AŞIMI"
        elif result.output_limit_exceeded:
            status = "ÇIKTI SINIRI"
        elif spec.kind in {CommandKind.UNITTEST, CommandKind.PYTEST}:
            if not summary or not summary.total:
                status = "TEST BULUNAMADI" if result.succeeded else "BAŞARISIZ"
        return (
            f"TERMİNAL RAPORU\nDurum: {status}\nKomut: {' '.join(spec.arguments)}"
            f"\nÇıkış kodu: {result.exit_code}\nSüre: {result.duration_seconds:.2f} sn"
            + (f"\nTest: {summary.passed}/{summary.total}" if summary else "")
            + f"\n{result.output[:8000]}"
        )

    def _parse(self, command):
        if len(command) > 1000 or re.search(r"[;&|><`$\r\n]", command):
            raise ValueError("Shell operatörleri ve çoklu komutlar desteklenmez.")
        match = self._COMMAND.fullmatch(command)
        if not match:
            raise ValueError(self._USAGE)
        kind = CommandKind(match.group(1).casefold())
        target = (match.group(2) or "").strip()
        if kind is CommandKind.RUFF:
            if target != "check" and not target.startswith("check "):
                raise ValueError("Ruff yalnızca check işlemini destekler.")
            target = target[5:].strip()
        if target:
            # Existing safe policy rejects flags, absolute paths and traversal.
            SafeCommandPolicy().build(CommandRequest(kind, target))
            self._resolver.resolve(target)
        return SafeCommandPolicy().build(CommandRequest(kind, target))
