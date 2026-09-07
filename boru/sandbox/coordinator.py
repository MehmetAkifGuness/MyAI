from boru.tools.command_models import CommandKind, CommandRequest
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.test_results import TestOutputParser


class SandboxCoordinator:
    def __init__(self, executor):
        self._executor = executor

    def resolve(self, message: str) -> str | None:
        normalized = " ".join(message.strip().casefold().split())
        if normalized == "sandbox durumu":
            return self._executor.status()
        if not normalized.startswith("sandbox"):
            return None
        prefix, separator, target = message.partition(":")
        if not separator or prefix.strip().casefold() != "sandbox test":
            return "Biçimler: sandbox durumu; sandbox test: tests/test_ornek.py"
        try:
            spec = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, target.strip()))
            result = self._executor.execute(spec)
        except (OSError, ValueError) as error:
            return f"SANDBOX RAPORU\nDurum: ÇALIŞTIRILAMADI\n{error}"
        summary = TestOutputParser().parse(result)
        status = "BAŞARILI" if result.succeeded and summary and summary.total else "BAŞARISIZ"
        return f"SANDBOX RAPORU\nDurum: {status}\n{result.output[:8000]}"
