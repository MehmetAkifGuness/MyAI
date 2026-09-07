from pathlib import Path
from typing import Protocol

from boru.tools.arguments import ToolArgumentSchema, ToolArgumentSpec, ToolArgumentType
from boru.tools.command_models import CommandExecutionResult, CommandKind, CommandRequest
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.models import ToolResult, ToolRisk
from boru.tools.test_results import TestOutputParser
from boru.tools.workspace import WorkspacePathResolver


class SandboxCommandExecutor(Protocol):
    def execute(self, command) -> CommandExecutionResult:
        ...


class TargetedSandboxTestTool:
    """Run one existing test file through a canonical command in the Docker sandbox."""

    _RUNNERS = {
        "unittest": CommandKind.UNITTEST,
        "pytest": CommandKind.PYTEST,
    }

    def __init__(
        self,
        root: str | Path,
        executor: SandboxCommandExecutor,
        *,
        max_output_characters: int = 6000,
    ) -> None:
        if max_output_characters < 500 or max_output_characters > 20000:
            raise ValueError("Sandbox test çıktı sınırı 500 ile 20000 arasında olmalıdır.")
        self._resolver = WorkspacePathResolver(root)
        self._executor = executor
        self._max_output_characters = max_output_characters

    @property
    def name(self) -> str:
        return "run_targeted_test"

    @property
    def description(self) -> str:
        return (
            "Mevcut tek bir unittest veya pytest dosyasını ağsız, salt-okunur Docker "
            "sandbox içinde çalıştırır. Argümanlar: path, runner. Serbest shell çalıştırmaz."
        )

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.EXECUTION

    @property
    def argument_schema(self) -> ToolArgumentSchema:
        return ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    "path",
                    ToolArgumentType.STRING,
                    strip=True,
                    allow_empty=False,
                    max_length=1024,
                ),
                ToolArgumentSpec(
                    "runner",
                    ToolArgumentType.STRING,
                    required=False,
                    strip=True,
                    allow_empty=False,
                    max_length=16,
                    has_default=True,
                    default="unittest",
                ),
            )
        )

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        path = arguments["path"]
        runner = arguments["runner"]
        if not isinstance(path, str) or not isinstance(runner, str):
            raise ValueError("Sandbox test path ve runner argümanları metin olmalıdır.")
        normalized = self._validated_test_path(path)
        kind = self._RUNNERS.get(runner.casefold())
        if kind is None:
            raise ValueError("Sandbox test runner yalnızca unittest veya pytest olabilir.")
        command = SafeCommandPolicy().build(CommandRequest(kind, normalized))
        result = self._executor.execute(command)
        summary = TestOutputParser().parse(result)
        status = self._status(result, summary)
        excerpt = result.output[-self._max_output_characters :].strip()
        counts = self._summary_metadata(summary)
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=self._render(normalized, runner.casefold(), status, result, counts, excerpt),
            metadata={
                "path": normalized,
                "runner": runner.casefold(),
                "status": status,
                "exit_code": result.exit_code,
                "duration_seconds": result.duration_seconds,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit_exceeded,
                "summary": counts,
                "output_excerpt": excerpt,
                "absence_is_evidence": True,
            },
        )

    def _validated_test_path(self, path: str) -> str:
        target = self._resolver.resolve(path)
        if not target.is_file() or target.suffix.casefold() != ".py":
            raise ValueError("Sandbox test hedefi mevcut bir Python dosyası olmalıdır.")
        relative = target.relative_to(self._resolver.root).as_posix()
        name = target.name.casefold()
        directories = {part.casefold() for part in Path(relative).parts[:-1]}
        if not (name.startswith("test_") or name.endswith("_test.py") or "tests" in directories):
            raise ValueError("Sandbox aracı yalnızca açık test dosyalarını çalıştırabilir.")
        return relative

    @staticmethod
    def _status(result: CommandExecutionResult, summary) -> str:
        if result.timed_out or result.output_limit_exceeded or summary is None:
            return "KANIT YETERSİZ"
        if result.succeeded and summary.total and not summary.failed:
            return "GEÇTİ"
        return "BAŞARISIZ"

    @staticmethod
    def _summary_metadata(summary) -> dict[str, object]:
        if summary is None:
            return {}
        return {
            "framework": summary.framework,
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "skipped": summary.skipped,
        }

    @staticmethod
    def _render(path, runner, status, result, counts, excerpt) -> str:
        summary = (
            f"toplam={counts.get('total')}, geçti={counts.get('passed')}, "
            f"başarısız={counts.get('failed')}, atlandı={counts.get('skipped')}"
            if counts
            else "ayrıştırılamadı"
        )
        return (
            "SANDBOX TEST KANITI\n"
            f"Hedef: {path}\nRunner: {runner}\nDurum: {status}\n"
            f"Çıkış kodu: {result.exit_code}\nSüre: {result.duration_seconds:.2f} sn\n"
            f"Özet: {summary}\nÇıktı:\n{excerpt or '(çıktı yok)'}"
        )
