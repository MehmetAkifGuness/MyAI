import sys
import tempfile
import unittest
from pathlib import Path

from boru.memory import ConservativeMemoryDecisionGate
from boru.tools import (
    BoundedCommandExecutor,
    CommandExecutionResult,
    CommandKind,
    CommandRequest,
    CommandRisk,
    CommandSpec,
    RuleBasedCommandRequestParser,
    SafeCommandCoordinator,
    SafeCommandPolicy,
    TestOutputParser,
)


class CommandParserAndPolicyTests(unittest.TestCase):
    def test_parses_only_supported_command_formats(self) -> None:
        parser = RuleBasedCommandRequestParser()
        cases = (
            ("testleri çalıştır", CommandKind.UNITTEST, ""),
            ("unittest çalıştır: tests.test_v123", CommandKind.UNITTEST, "tests.test_v123"),
            ("pytest çalıştır: tests/test_v123.py", CommandKind.PYTEST, "tests/test_v123.py"),
            ("ruff kontrolü çalıştır: boru", CommandKind.RUFF, "boru"),
            ("mypy çalıştır", CommandKind.MYPY, ""),
        )

        for message, kind, target in cases:
            with self.subTest(message=message):
                request = parser.parse(message)
                self.assertEqual(request, CommandRequest(kind, target))

    def test_injection_and_traversal_fail_closed(self) -> None:
        parser = RuleBasedCommandRequestParser()
        for message in (
            "pytest çalıştır: tests;whoami",
            "pytest çalıştır: ../outside",
            "komut çalıştır: rm -rf /",
        ):
            with self.subTest(message=message):
                if "../" in message:
                    with self.assertRaises(ValueError):
                        parser.parse(message)
                else:
                    self.assertIsNone(parser.parse(message))
                self.assertTrue(parser.is_command_intent(message))

    def test_policy_builds_fixed_python_vectors(self) -> None:
        policy = SafeCommandPolicy()
        cases = (
            (CommandKind.UNITTEST, "", ("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py")),
            (CommandKind.PYTEST, "tests", ("-m", "pytest", "tests")),
            (CommandKind.RUFF, "boru", ("-m", "ruff", "check", "boru")),
            (CommandKind.MYPY, "", ("-m", "mypy", "boru")),
        )

        for kind, target, expected in cases:
            with self.subTest(kind=kind):
                command = policy.build(CommandRequest(kind, target))
                self.assertEqual(command.executable, sys.executable)
                self.assertEqual(command.arguments, expected)
                self.assertIs(command.risk, CommandRisk.SAFE)

    def test_policy_rejects_untrusted_direct_request(self) -> None:
        for target in ("../outside", "tests;whoami", "/absolute"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    SafeCommandPolicy().build(
                        CommandRequest(CommandKind.PYTEST, target)
                    )

    def test_memory_gate_rejects_command_tasks(self) -> None:
        gate = ConservativeMemoryDecisionGate()
        self.assertFalse(gate.should_evaluate("testleri çalıştır"))
        self.assertFalse(gate.should_evaluate("terminal komutu çalıştır"))


class BoundedCommandExecutorTests(unittest.TestCase):
    @staticmethod
    def _python_spec(code: str) -> CommandSpec:
        return CommandSpec(
            kind=CommandKind.UNITTEST,
            executable=sys.executable,
            arguments=("-c", code),
            display="bounded test helper",
            risk=CommandRisk.SAFE,
        )

    def test_runs_unittest_and_parses_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_sample.py").write_text(
                "import unittest\n\nclass Sample(unittest.TestCase):\n"
                "    def test_ok(self):\n        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            command = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST))
            result = BoundedCommandExecutor(root, timeout_seconds=5).execute(command)
            summary = TestOutputParser().parse(result)

            self.assertTrue(result.succeeded, result.output)
            self.assertIsNotNone(summary)
            self.assertEqual((summary.total, summary.passed, summary.failed), (1, 1, 0))

    def test_reports_failing_unittest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = BoundedCommandExecutor(Path(directory)).execute(
                self._python_spec(
                    "import sys; print('Ran 1 test in 0.01s'); "
                    "print('FAILED (failures=1)'); sys.exit(1)"
                )
            )
            summary = TestOutputParser().parse(result)

            self.assertFalse(result.succeeded)
            self.assertEqual((summary.total, summary.passed, summary.failed), (1, 0, 1))

    def test_enforces_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = BoundedCommandExecutor(
                Path(directory),
                timeout_seconds=0.1,
            ).execute(self._python_spec("import time; time.sleep(2)"))

            self.assertTrue(result.timed_out)
            self.assertFalse(result.succeeded)

    def test_enforces_output_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = BoundedCommandExecutor(
                Path(directory),
                max_output_bytes=128,
            ).execute(self._python_spec("print('x' * 10000)"))

            self.assertTrue(result.output_limit_exceeded)
            self.assertTrue(result.truncated)
            self.assertLessEqual(len(result.output.encode("utf-8")), 128)


class RecordingExecutor:
    def __init__(self) -> None:
        self.commands: list[CommandSpec] = []

    def execute(self, command: CommandSpec) -> CommandExecutionResult:
        self.commands.append(command)
        return CommandExecutionResult(
            command=command,
            exit_code=0,
            duration_seconds=0.25,
            output="Ran 2 tests in 0.01s\n\nOK",
        )


class SafeCommandCoordinatorTests(unittest.TestCase):
    def build_coordinator(self, executor: RecordingExecutor) -> SafeCommandCoordinator:
        return SafeCommandCoordinator(
            parser=RuleBasedCommandRequestParser(),
            policy=SafeCommandPolicy(),
            executor=executor,
            result_parser=TestOutputParser(),
        )

    def test_formats_test_result(self) -> None:
        executor = RecordingExecutor()
        response = self.build_coordinator(executor).resolve("testleri çalıştır")

        self.assertIn("Durum: BAŞARILI", response or "")
        self.assertIn("2/2 geçti", response or "")
        self.assertEqual(len(executor.commands), 1)

    def test_arbitrary_command_never_reaches_executor(self) -> None:
        executor = RecordingExecutor()
        response = self.build_coordinator(executor).resolve("komut çalıştır: rm -rf /")

        self.assertIn("Serbest sistem komutları çalıştırılmaz", response or "")
        self.assertEqual(executor.commands, [])


if __name__ == "__main__":
    unittest.main()
