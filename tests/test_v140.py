import shutil
import subprocess
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
    ControlledGitCoordinator,
    GitCommandPolicy,
    RuleBasedGitRequestParser,
)


class GitParserAndPolicyTests(unittest.TestCase):
    def test_parses_supported_read_and_write_operations(self) -> None:
        parser = RuleBasedGitRequestParser()
        cases = (
            ("git durum", CommandKind.GIT_STATUS, ""),
            ("git fark", CommandKind.GIT_DIFF, ""),
            ("git dalları", CommandKind.GIT_BRANCH, ""),
            ("git geçmişi", CommandKind.GIT_LOG, ""),
            ("git ekle: boru/app.py", CommandKind.GIT_ADD, "boru/app.py"),
            ("git commit: feat: güvenli Git", CommandKind.GIT_COMMIT, "feat: güvenli Git"),
            ("git geri al: boru/app.py", CommandKind.GIT_RESTORE, "boru/app.py"),
        )

        for message, kind, target in cases:
            with self.subTest(message=message):
                self.assertEqual(parser.parse(message), CommandRequest(kind, target))

    def test_rejects_unsafe_paths_and_detects_unknown_git_intent(self) -> None:
        parser = RuleBasedGitRequestParser()
        for message in (
            "git ekle: ../secret.txt",
            "git geri al: .git/config",
            "git ekle: file.txt;whoami",
        ):
            with self.subTest(message=message):
                with self.assertRaises(ValueError):
                    parser.parse(message)
        self.assertIsNone(parser.parse("git reset --hard"))
        self.assertTrue(parser.is_command_intent("git reset --hard"))

    def test_policy_builds_fixed_vectors_and_risks(self) -> None:
        policy = GitCommandPolicy()
        cases = (
            (CommandRequest(CommandKind.GIT_STATUS), ("status", "--short", "--branch"), CommandRisk.SAFE),
            (CommandRequest(CommandKind.GIT_DIFF), ("diff", "--"), CommandRisk.SAFE),
            (CommandRequest(CommandKind.GIT_BRANCH), ("branch", "--list"), CommandRisk.SAFE),
            (CommandRequest(CommandKind.GIT_LOG), ("log", "-n", "20", "--oneline", "--decorate"), CommandRisk.SAFE),
            (CommandRequest(CommandKind.GIT_ADD, "a.txt"), ("add", "--", "a.txt"), CommandRisk.REQUIRES_APPROVAL),
            (CommandRequest(CommandKind.GIT_COMMIT, "feat: test"), ("commit", "-m", "feat: test"), CommandRisk.REQUIRES_APPROVAL),
            (CommandRequest(CommandKind.GIT_RESTORE, "a.txt"), ("restore", "--", "a.txt"), CommandRisk.REQUIRES_APPROVAL),
        )

        for request, arguments, risk in cases:
            with self.subTest(kind=request.kind):
                command = policy.build(request)
                self.assertEqual(command.arguments, arguments)
                self.assertIs(command.risk, risk)
                self.assertTrue(Path(command.executable).is_absolute())

    def test_policy_revalidates_direct_requests(self) -> None:
        with self.assertRaises(ValueError):
            GitCommandPolicy().build(CommandRequest(CommandKind.GIT_ADD, "../outside"))

    def test_memory_gate_rejects_git_tasks(self) -> None:
        gate = ConservativeMemoryDecisionGate()
        self.assertFalse(gate.should_evaluate("git durum"))
        self.assertFalse(gate.should_evaluate("git commit: feat: test"))


class RecordingGitExecutor:
    def __init__(self) -> None:
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        return CommandExecutionResult(command, 0, 0.1, "clean")


class ControlledGitCoordinatorTests(unittest.TestCase):
    @staticmethod
    def build(executor) -> ControlledGitCoordinator:
        return ControlledGitCoordinator(
            parser=RuleBasedGitRequestParser(),
            policy=GitCommandPolicy(),
            executor=executor,
        )

    def test_read_operation_executes_without_approval(self) -> None:
        executor = RecordingGitExecutor()
        response = self.build(executor).resolve("git durum")
        self.assertIn("Durum: BAŞARILI", response or "")
        self.assertEqual(len(executor.commands), 1)

    def test_add_and_commit_require_explicit_approval(self) -> None:
        for message in ("git ekle: a.txt", "git commit: feat: test"):
            with self.subTest(message=message):
                executor = RecordingGitExecutor()
                coordinator = self.build(executor)
                preview = coordinator.resolve(message)
                self.assertIn("Risk: WRITE", preview or "")
                self.assertEqual(executor.commands, [])
                self.assertIn("onay bekleyen", coordinator.resolve("onayla"))
                result = coordinator.resolve("git işlemini onayla")
                self.assertIn("Durum: BAŞARILI", result)
                self.assertEqual(len(executor.commands), 1)

    def test_restore_requires_high_risk_confirmation(self) -> None:
        executor = RecordingGitExecutor()
        coordinator = self.build(executor)
        preview = coordinator.resolve("git geri al: a.txt")
        self.assertIn("Risk: DESTRUCTIVE", preview or "")
        self.assertIn("git geri almayı onayla", coordinator.resolve("git işlemini onayla"))
        coordinator.resolve("git geri almayı onayla")
        self.assertEqual(len(executor.commands), 1)

    def test_unknown_git_command_fails_closed(self) -> None:
        executor = RecordingGitExecutor()
        response = self.build(executor).resolve("git reset --hard")
        self.assertIn("Serbest Git argümanları çalıştırılmaz", response or "")
        self.assertEqual(executor.commands, [])


@unittest.skipUnless(shutil.which("git"), "Git executable gerekli")
class GitIntegrationTests(unittest.TestCase):
    def test_add_commit_and_restore_in_temporary_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "--quiet")
            self._git(root, "config", "user.name", "Boru Test")
            self._git(root, "config", "user.email", "boru@example.invalid")
            target = root / "sample.txt"
            target.write_text("first\n", encoding="utf-8")
            coordinator = ControlledGitCoordinator(
                parser=RuleBasedGitRequestParser(),
                policy=GitCommandPolicy(),
                executor=BoundedCommandExecutor(
                    root,
                    timeout_seconds=10,
                    allowed_risks=(CommandRisk.SAFE, CommandRisk.REQUIRES_APPROVAL),
                ),
            )

            coordinator.resolve("git ekle: sample.txt")
            self.assertIn("BAŞARILI", coordinator.resolve("git işlemini onayla"))
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only"), "sample.txt")

            coordinator.resolve("git commit: test: initial")
            self.assertIn("BAŞARILI", coordinator.resolve("git işlemini onayla"))
            target.write_text("changed\n", encoding="utf-8")

            coordinator.resolve("git geri al: sample.txt")
            self.assertIn("BAŞARILI", coordinator.resolve("git geri almayı onayla"))
            self.assertEqual(target.read_text(encoding="utf-8"), "first\n")

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        result = subprocess.run(
            (shutil.which("git"), *arguments),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
