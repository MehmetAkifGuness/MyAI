import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.agent import ReadOnlyToolAgent
from boru.code_index import CodeSearchTool, SafeCodeIndex
from boru.release import build_release
from boru.sandbox import TargetedSandboxTestTool
from boru.tools import (
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
)
from boru.tools.command_models import CommandExecutionResult


class FakeSandboxExecutor:
    def __init__(self, output, exit_code):
        self.output = output
        self.exit_code = exit_code
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        return CommandExecutionResult(
            command=command,
            exit_code=self.exit_code,
            duration_seconds=0.25,
            output=self.output,
        )


class UnusedModel:
    def generate(self, messages):
        raise AssertionError("Hedefli test raporu model üretimi kullanmamalıdır.")

    def generate_structured(self, messages, schema):
        raise AssertionError("Hedefli test raporu structured model kullanmamalıdır.")


class TargetedSandboxTestToolTests(unittest.TestCase):
    _FAILURE = (
        "F\n"
        "======================================================================\n"
        "FAIL: test_add (sample_test.MathTests.test_add)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        "  File \"/workspace/sample_test.py\", line 6, in test_add\n"
        "    self.assertEqual(add(2, 3), 5)\n"
        "AssertionError: -1 != 5\n"
        "----------------------------------------------------------------------\n"
        "Ran 1 test in 0.001s\n\nFAILED (failures=1)\n"
    )

    def test_failed_test_is_successful_tool_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample_test.py").write_text(
                "import unittest\nclass MathTests(unittest.TestCase):\n"
                "    def test_add(self):\n        self.fail()\n",
                encoding="utf-8",
            )
            sandbox = FakeSandboxExecutor(self._FAILURE, 1)
            tool = TargetedSandboxTestTool(root, sandbox)

            result = tool.execute({"path": "sample_test.py", "runner": "unittest"})

            self.assertTrue(result.success)
            self.assertEqual(result.metadata["status"], "BAŞARISIZ")
            self.assertEqual(result.metadata["summary"]["failed"], 1)
            self.assertIn("AssertionError: -1 != 5", result.content)
            self.assertEqual(sandbox.commands[0].arguments[-1], "sample_test.py")

    def test_rejects_non_test_python_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "application.py").write_text("VALUE = 1\n", encoding="utf-8")
            tool = TargetedSandboxTestTool(root, FakeSandboxExecutor("", 0))

            with self.assertRaisesRegex(ValueError, "yalnızca açık test"):
                tool.execute({"path": "application.py", "runner": "unittest"})

    def test_agent_runs_test_and_renders_failure_without_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample_test.py").write_text(
                "import unittest\nclass MathTests(unittest.TestCase):\n"
                "    def test_add(self):\n        self.fail()\n",
                encoding="utf-8",
            )
            workspace = ReadOnlyWorkspace(root)
            registry = ToolRegistry(
                [
                    ReadFileTool(workspace),
                    CodeSearchTool(SafeCodeIndex(root)),
                    TargetedSandboxTestTool(
                        root,
                        FakeSandboxExecutor(self._FAILURE, 1),
                    ),
                ]
            )
            executor = ToolExecutor(
                registry,
                RiskBasedToolPolicy(
                    (ToolRisk.SAFE, ToolRisk.READ_ONLY, ToolRisk.EXECUTION)
                ),
            )

            report = ReadOnlyToolAgent(UnusedModel(), registry, executor).run(
                "sample_test.py testini sandbox içinde çalıştır ve sonucu açıkla"
            )

            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn("Durum: BAŞARISIZ", report)
            self.assertIn("AssertionError: -1 != 5", report)
            self.assertIn("run_targeted_test — sample_test.py", report)


class ReleaseV160Tests(unittest.TestCase):
    def test_runtime_test_agent_requires_general_agent_and_sandbox(self):
        with self.assertRaisesRegex(ValueError, "genel ajan ve Docker sandbox"):
            main_v170.build_application(runtime_test_agent_enabled=True)

    def test_default_release_enables_runtime_test_agent(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release(), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V1.6")
            self.assertTrue(flags["sandbox_enabled"])
            self.assertTrue(flags["runtime_test_agent_enabled"])


if __name__ == "__main__":
    unittest.main()
