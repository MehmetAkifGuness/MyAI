import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from boru.sandbox import DockerSandboxExecutor, SourceSnapshot
from boru.sandbox.coordinator import SandboxCoordinator
from boru.tools.command_models import CommandExecutionResult, CommandKind, CommandRequest, CommandRisk, CommandSpec
from boru.tools.command_policy import SafeCommandPolicy
from boru.tools.command_executor import BoundedCommandExecutor


class SandboxTests(unittest.TestCase):
    def test_snapshot_excludes_runtime_data_secrets_and_links(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as target:
            root = Path(directory)
            for path in ("a.py", "tests/test_a.py", "data/memory.json", ".env", "secret.key", ".git/info.txt"):
                item = root / path
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_text("VALUE = 1", encoding="utf-8")
            contents = SourceSnapshot(root).copy_to(Path(target))
            self.assertEqual(set(contents), {"a.py", "tests/test_a.py"})
            self.assertFalse((Path(target) / "data").exists())

    def test_snapshot_limit_fails_instead_of_truncating_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("VALUE = 1", encoding="utf-8")
            with self.assertRaises(ValueError):
                SourceSnapshot(root, max_bytes=2).read_sources()

    def test_forged_command_is_rejected(self):
        spec = CommandSpec(CommandKind.UNITTEST, "python", ("-c", "print('bad')"), "forged", CommandRisk.SAFE)
        with self.assertRaises(ValueError):
            DockerSandboxExecutor._canonical_arguments(spec)

    def test_windows_test_paths_are_normalized_for_linux(self):
        spec = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, r"tests\test_a.py"))
        self.assertEqual(DockerSandboxExecutor._canonical_arguments(spec)[-1], "tests/test_a.py")

    def test_container_uses_readonly_copy_and_cleans_up_on_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("VALUE = 1", encoding="utf-8")
            specs = []

            class Runner:
                def execute(self, spec):
                    specs.append(spec)
                    return CommandExecutionResult(spec, -1, 120, "timeout", timed_out=True)

            executor = DockerSandboxExecutor(root, runner=Runner(), docker="docker")
            spec = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, "tests.test_a"))
            with patch.object(executor, "_check"), patch.object(executor, "_cleanup") as cleanup:
                result = executor.execute(spec)
            self.assertTrue(result.timed_out)
            self.assertEqual(result.command, spec)
            cleanup.assert_called_once()
            args = specs[0].arguments
            for flag in ("--network=none", "--read-only", "--cap-drop=ALL", "--pids-limit=64", "--pull=never"):
                self.assertIn(flag, args)
            mount = args[args.index("--mount") + 1]
            self.assertNotIn(str(root), mount)
            self.assertIn("readonly", mount)
            self.assertEqual((root / "a.py").read_text(), "VALUE = 1")

    def test_unavailable_docker_never_falls_back_to_host(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = DockerSandboxExecutor(Path(directory))
            executor._docker = None
            response = SandboxCoordinator(executor).resolve("sandbox test: tests/test_a.py")
            self.assertIn("ÇALIŞTIRILAMADI", response)
            self.assertIn("HAZIR DEĞİL", executor.status())


@unittest.skipUnless(os.getenv("BORU_RUN_DOCKER_TESTS") == "1", "Docker canlı testi isteğe bağlı")
class LiveSandboxTests(unittest.TestCase):
    def test_timeout_removes_its_container(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/__init__.py").write_text("", encoding="utf-8")
            (root / "tests/test_loop.py").write_text(
                "import time, unittest\nclass LoopTests(unittest.TestCase):\n"
                "    def test_wait(self):\n        time.sleep(60)\n", encoding="utf-8")
            executor = DockerSandboxExecutor(root, runner=BoundedCommandExecutor(root, timeout_seconds=2))
            command = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, "tests.test_loop"))
            with patch.object(executor, "_cleanup", wraps=executor._cleanup) as cleanup:
                result = executor.execute(command)
            self.assertTrue(result.timed_out, result.output)
            name = cleanup.call_args.args[0]
            check = subprocess.run((executor._docker, "container", "inspect", name),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
            self.assertNotEqual(check.returncode, 0)
            self.assertIn(b"No such", check.stderr)

    def test_real_container_passes_isolation_assertions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/__init__.py").write_text("", encoding="utf-8")
            (root / "sentinel.txt").write_text("unchanged", encoding="utf-8")
            (root / "tests/test_isolation.py").write_text(
                "import os, socket, unittest\nfrom pathlib import Path\n"
                "class IsolationTests(unittest.TestCase):\n"
                "    def test_boundaries(self):\n"
                "        self.assertNotEqual(os.getuid(), 0)\n"
                "        self.assertFalse(Path('/var/run/docker.sock').exists())\n"
                "        self.assertIsNone(os.getenv('BORU_HOST_SENTINEL'))\n"
                "        with self.assertRaises(OSError):\n"
                "            Path('/workspace/sentinel.txt').write_text('modified')\n"
                "        with self.assertRaises(OSError):\n"
                "            socket.create_connection(('1.1.1.1', 443), timeout=1)\n",
                encoding="utf-8")
            executor = DockerSandboxExecutor(root, os.getenv("BORU_SANDBOX_IMAGE", "boru-sandbox:1.0"))
            command = SafeCommandPolicy().build(CommandRequest(CommandKind.UNITTEST, "tests.test_isolation"))
            with patch.dict(os.environ, {"BORU_HOST_SENTINEL": "not-for-container"}):
                result = executor.execute(command)
            self.assertTrue(result.succeeded, result.output)
            self.assertIn("Ran 1 test", result.output)
            self.assertEqual((root / "sentinel.txt").read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
