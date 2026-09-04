import tempfile
import unittest
from pathlib import Path

from boru.tools import (
    BoundedCommandExecutor,
    CommandExecutionResult,
    CommandKind,
    CommandRequest,
    ControlledAutoFixCoordinator,
    EditOutcome,
    EditProposal,
    ExclusiveOperationCoordinator,
    ProjectEditOutcome,
    ProjectEditProposal,
    RuleBasedAutoFixRequestParser,
    RuleBasedCommandRequestParser,
    SafeCommandPolicy,
    SafeEditWorkspace,
    TestOutputParser,
    BatchProjectEditApplier,
)


def proposal_for(content: str = "fixed") -> ProjectEditProposal:
    return ProjectEditProposal(
        instruction="fix failure",
        edits=(
            EditProposal(
                path="app.py",
                updated_content=content,
                expected_sha256="hash",
                diff="- broken\n+ fixed",
                original_character_count=6,
                updated_character_count=len(content),
            ),
        ),
    )


class RecordingPreparer:
    def __init__(self, proposal: ProjectEditProposal | None = None) -> None:
        self.proposal = proposal or proposal_for()
        self.requests = []

    def prepare_project_edit(self, request):
        self.requests.append(request)
        return self.proposal


class RecordingApplier:
    def __init__(self) -> None:
        self.proposals = []

    def apply_project_edit(self, proposal):
        self.proposals.append(proposal)
        return ProjectEditOutcome((EditOutcome("app.py", 5, 5),))


class SequencedExecutor:
    def __init__(self, successes, *, timed_out: bool = False) -> None:
        self.successes = list(successes)
        self.timed_out = timed_out
        self.calls = 0

    def execute(self, command):
        success = self.successes[min(self.calls, len(self.successes) - 1)]
        self.calls += 1
        output = "Ran 1 test in 0.01s\n\nOK" if success else "Ran 1 test in 0.01s\nFAILED (failures=1)"
        return CommandExecutionResult(
            command=command,
            exit_code=0 if success else 1,
            duration_seconds=0.01,
            output=output,
            timed_out=self.timed_out,
        )


def build_coordinator(executor, preparer=None, applier=None, max_attempts=3):
    return ControlledAutoFixCoordinator(
        parser=RuleBasedAutoFixRequestParser(RuleBasedCommandRequestParser()),
        command_policy=SafeCommandPolicy(),
        command_executor=executor,
        result_parser=TestOutputParser(),
        proposal_preparer=preparer or RecordingPreparer(),
        proposal_applier=applier or RecordingApplier(),
        max_fix_attempts=max_attempts,
    )


class AutoFixParserTests(unittest.TestCase):
    def test_parses_supported_nested_test_command(self) -> None:
        parser = RuleBasedAutoFixRequestParser(RuleBasedCommandRequestParser())
        request = parser.parse(
            "otomatik düzelt: unittest çalıştır: tests.test_sample"
        )
        self.assertEqual(
            request,
            CommandRequest(CommandKind.UNITTEST, "tests.test_sample"),
        )

    def test_rejects_arbitrary_nested_command(self) -> None:
        parser = RuleBasedAutoFixRequestParser(RuleBasedCommandRequestParser())
        with self.assertRaises(ValueError):
            parser.parse("otomatik düzelt: python -c whoami")
        self.assertTrue(parser.is_command_intent("otomatik düzelt: bir şey yap"))


class AutoFixStateMachineTests(unittest.TestCase):
    def test_passing_test_never_prepares_or_applies_change(self) -> None:
        preparer = RecordingPreparer()
        applier = RecordingApplier()
        response = build_coordinator(
            SequencedExecutor([True]), preparer, applier
        ).resolve("otomatik düzelt: testleri çalıştır")
        self.assertIn("zaten başarılı", response or "")
        self.assertEqual(preparer.requests, [])
        self.assertEqual(applier.proposals, [])

    def test_failure_requires_approval_then_retests(self) -> None:
        preparer = RecordingPreparer()
        applier = RecordingApplier()
        coordinator = build_coordinator(
            SequencedExecutor([False, True]), preparer, applier
        )
        preview = coordinator.resolve("otomatik düzelt: testleri çalıştır")
        self.assertIn("henüz uygulanmadı", preview or "")
        self.assertTrue(coordinator.has_pending)
        self.assertEqual(applier.proposals, [])
        self.assertIn("Onay bekleyen", coordinator.resolve("onayla"))

        result = coordinator.resolve("otomatik düzeltmeyi onayla")
        self.assertIn("Otomatik düzeltme tamamlandı", result)
        self.assertIn("1/1 geçti", result)
        self.assertEqual(len(applier.proposals), 1)
        self.assertFalse(coordinator.has_pending)

    def test_cancel_preserves_files(self) -> None:
        applier = RecordingApplier()
        coordinator = build_coordinator(SequencedExecutor([False]), applier=applier)
        coordinator.resolve("otomatik düzelt: testleri çalıştır")
        response = coordinator.resolve("iptal")
        self.assertIn("hiçbir öneri uygulanmadı", response)
        self.assertEqual(applier.proposals, [])

    def test_timeout_stops_without_preparing_change(self) -> None:
        preparer = RecordingPreparer()
        response = build_coordinator(
            SequencedExecutor([False], timed_out=True), preparer=preparer
        ).resolve("otomatik düzelt: testleri çalıştır")
        self.assertIn("kod değiştirmeden durduruldu", response or "")
        self.assertEqual(preparer.requests, [])

    def test_stops_after_three_failed_fixes(self) -> None:
        preparer = RecordingPreparer()
        applier = RecordingApplier()
        coordinator = build_coordinator(
            SequencedExecutor([False, False, False, False]),
            preparer,
            applier,
            max_attempts=3,
        )
        coordinator.resolve("otomatik düzelt: testleri çalıştır")
        for _ in range(2):
            response = coordinator.resolve("otomatik düzeltmeyi onayla")
            self.assertIn("hâlâ başarısız", response)
        response = coordinator.resolve("otomatik düzeltmeyi onayla")
        self.assertIn("3 denemeden sonra durdu", response)
        self.assertEqual(len(applier.proposals), 3)
        self.assertFalse(coordinator.has_pending)


class WorkspaceFixPreparer:
    def __init__(self, workspace: SafeEditWorkspace) -> None:
        self.workspace = workspace

    def prepare_project_edit(self, request):
        source = self.workspace.read_edit_source("app.py")
        updated = "def answer():\n    return 42\n"
        return ProjectEditProposal(
            instruction=request.instruction,
            edits=(
                EditProposal(
                    path="app.py",
                    updated_content=updated,
                    expected_sha256=source.sha256,
                    diff="- return 0\n+ return 42",
                    original_character_count=len(source.content),
                    updated_character_count=len(updated),
                ),
            ),
        )


class AutoFixIntegrationTests(unittest.TestCase):
    def test_failing_test_is_fixed_only_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (root / "app.py").write_text(
                "def answer():\n    return 0\n", encoding="utf-8"
            )
            (root / "tests" / "test_sample.py").write_text(
                "import unittest\nfrom app import answer\n\n"
                "class Sample(unittest.TestCase):\n"
                "    def test_answer(self):\n"
                "        self.assertEqual(answer(), 42)\n",
                encoding="utf-8",
            )
            workspace = SafeEditWorkspace(root)
            coordinator = ControlledAutoFixCoordinator(
                parser=RuleBasedAutoFixRequestParser(RuleBasedCommandRequestParser()),
                command_policy=SafeCommandPolicy(),
                command_executor=BoundedCommandExecutor(root, timeout_seconds=5),
                result_parser=TestOutputParser(),
                proposal_preparer=WorkspaceFixPreparer(workspace),
                proposal_applier=BatchProjectEditApplier(workspace=workspace),
            )

            preview = coordinator.resolve(
                "otomatik düzelt: unittest çalıştır: tests.test_sample"
            )
            self.assertIn("Test başarısız", preview or "")
            self.assertIn("return 0", (root / "app.py").read_text(encoding="utf-8"))
            result = coordinator.resolve("otomatik düzeltmeyi onayla")
            self.assertIn("Otomatik düzeltme tamamlandı", result)
            self.assertIn("return 42", (root / "app.py").read_text(encoding="utf-8"))


class StubPendingResolver:
    def __init__(self, trigger: str) -> None:
        self.trigger = trigger
        self.has_pending = False
        self.messages = []

    def resolve(self, message: str):
        self.messages.append(message)
        if message == self.trigger:
            self.has_pending = True
            return "started"
        if self.has_pending and message == "iptal":
            self.has_pending = False
            return "cancelled"
        if self.has_pending:
            return "pending"
        return None


class ExclusiveOperationCoordinatorTests(unittest.TestCase):
    def test_active_operation_blocks_other_mutation_resolvers(self) -> None:
        first = StubPendingResolver("start first")
        second = StubPendingResolver("start second")
        router = ExclusiveOperationCoordinator((first, second))
        self.assertEqual(router.resolve("start first"), "started")
        self.assertEqual(router.resolve("start second"), "pending")
        self.assertEqual(second.messages, [])
        self.assertEqual(router.resolve("iptal"), "cancelled")
        self.assertEqual(router.resolve("start second"), "started")


if __name__ == "__main__":
    unittest.main()
