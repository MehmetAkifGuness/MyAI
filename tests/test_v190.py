import tempfile
import unittest
from pathlib import Path

from boru.architecture import (
    ArchitecturePlan,
    ArchitectureRequest,
    ArchitectureStep,
    LLMArchitectAgent,
)
from boru.coding import ControlledCodingCoordinator, RuleBasedCodingRequestParser
from boru.memory import ConservativeMemoryDecisionGate
from boru.testing import (
    RelatedTestDiscovery,
    RelatedTestSelection,
    RuleBasedTestAgentRequestParser,
    SafeTestAgent,
)
from boru.tools import (
    CommandExecutionResult,
    CommandRisk,
    EditOutcome,
    EditProposal,
    ProjectEditOutcome,
    ProjectEditProposal,
    SafeCommandPolicy,
    TestOutputParser,
)


class TestAgentParserTests(unittest.TestCase):
    def test_parses_comma_separated_source_paths(self):
        request = RuleBasedTestAgentRequestParser().parse(
            "test ajanı: boru/service.py, boru/models.py"
        )

        self.assertEqual(
            request.source_paths,
            ("boru/service.py", "boru/models.py"),
        )

    def test_rejects_duplicate_paths(self):
        with self.assertRaisesRegex(ValueError, "birden fazla"):
            RuleBasedTestAgentRequestParser().parse("tester: a.py, A.py")

    def test_test_agent_request_is_not_memory_candidate(self):
        self.assertFalse(
            ConservativeMemoryDecisionGate().should_evaluate(
                "test ajanı: boru/service.py"
            )
        )


class MissingScopedFileTests(unittest.TestCase):
    def test_architect_rejects_missing_edit_target_before_model_call(self):
        class UnexpectedModel:
            def generate_structured(self, messages, schema):
                raise AssertionError((messages, schema))

        class EmptyIndex:
            def list_editable_files(self):
                return ()

        agent = LLMArchitectAgent(
            chat_model=UnexpectedModel(),
            file_index=EmptyIndex(),
            file_selector=object(),
            workspace=object(),
            creation_validator=object(),
            fast_scoped_plans=True,
        )

        with self.assertRaisesRegex(ValueError, "dosya bulunamadı"):
            agent.plan(
                ArchitectureRequest(
                    "missing.py içinde VALUE değerini yalnızca bu dosyada 3 yap",
                    ("missing.py",),
                )
            )

    def test_architect_allows_missing_scope_for_creation_request(self):
        class Model:
            def generate_structured(self, messages, schema):
                del messages, schema
                return (
                    '{"summary":"Yeni dosya", "existing_files":[], '
                    '"new_files":["new.py"], "steps":[{"title":"Oluştur", '
                    '"description":"Dosyayı oluştur", "files":["new.py"]}], '
                    '"risks":[], "tests":[], "notes":[]}'
                )

        class EmptyIndex:
            def list_editable_files(self):
                return ()

        class Selector:
            def select_files(self, *, request, available_paths):
                del request, available_paths
                return type("Selection", (), {"paths": ()})()

        class Validator:
            def validate_new_text_file(self, path, content):
                self.value = (path, content)

        plan = LLMArchitectAgent(
            chat_model=Model(),
            file_index=EmptyIndex(),
            file_selector=Selector(),
            workspace=object(),
            creation_validator=Validator(),
            max_attempts=1,
        ).plan(
            ArchitectureRequest(
                "new.py dosyasını oluştur, yalnızca bu dosya",
                ("new.py",),
            )
        )

        self.assertEqual(plan.new_files, ("new.py",))


class RelatedTestDiscoveryTests(unittest.TestCase):
    def test_discovers_test_by_source_symbol_and_ignores_unrelated_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "boru").mkdir()
            (root / "tests").mkdir()
            (root / "boru" / "service.py").write_text(
                "class OrderService:\n    pass\n",
                encoding="utf-8",
            )
            (root / "tests" / "test_service.py").write_text(
                "from boru.service import OrderService\n\n"
                "def test_service_exists():\n"
                "    assert OrderService\n",
                encoding="utf-8",
            )
            (root / "tests" / "test_other.py").write_text(
                "import unittest\n",
                encoding="utf-8",
            )

            selection = RelatedTestDiscovery(root).discover(("boru/service.py",))

            self.assertEqual(selection.source_paths, ("boru/service.py",))
            self.assertEqual(selection.test_paths, ("tests/test_service.py",))

    def test_selects_changed_test_file_directly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            target = root / "tests" / "test_feature.py"
            target.write_text(
                "def test_feature():\n    assert True\n",
                encoding="utf-8",
            )

            selection = RelatedTestDiscovery(root).discover(
                ("tests/test_feature.py",)
            )

            self.assertEqual(selection.test_paths, ("tests/test_feature.py",))

    def test_does_not_treat_test_suffix_as_executable_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "manual_test.py"
            target.write_text("VALUE = 3\n", encoding="utf-8")

            selection = RelatedTestDiscovery(root).discover(("manual_test.py",))

            self.assertEqual(selection.test_paths, ())

    def test_rejects_workspace_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "Workspace dışına"):
                RelatedTestDiscovery(directory).discover(("../outside.py",))


class StaticDiscovery:
    def __init__(self, tests=()):
        self.tests = tests
        self.calls = []

    def discover(self, source_paths):
        self.calls.append(source_paths)
        return RelatedTestSelection(source_paths, self.tests)


class ResultExecutor:
    def __init__(self, failing=()):
        self.failing = set(failing)
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        failed = command.arguments[-1] in self.failing
        output = (
            "F\nRan 1 test in 0.001s\nFAILED (failures=1)"
            if failed
            else ".\nRan 1 test in 0.001s\nOK"
        )
        return CommandExecutionResult(
            command=command,
            exit_code=1 if failed else 0,
            duration_seconds=0.01,
            output=output,
        )


def make_test_agent(discovery, executor):
    return SafeTestAgent(
        parser=RuleBasedTestAgentRequestParser(),
        discovery=discovery,
        policy=SafeCommandPolicy(),
        executor=executor,
        result_parser=TestOutputParser(),
    )


class TestAgentCoordinatorTests(unittest.TestCase):
    def test_runs_only_discovered_tests_through_safe_unittest_policy(self):
        discovery = StaticDiscovery(("tests/test_service.py",))
        executor = ResultExecutor()

        response = make_test_agent(discovery, executor).resolve("test ajanı: boru/service.py")

        self.assertIn("Durum: BAŞARILI", response or "")
        self.assertIn("1/1 test dosyası geçti", response or "")
        self.assertEqual(executor.commands[0].risk, CommandRisk.SAFE)
        self.assertEqual(
            executor.commands[0].arguments,
            ("-m", "unittest", "tests/test_service.py"),
        )

    def test_reports_failure_output(self):
        path = "tests/test_service.py"
        response = make_test_agent(
            StaticDiscovery((path,)),
            ResultExecutor((path,)),
        ).run_for_paths(("boru/service.py",))

        self.assertIn("Durum: BAŞARISIZ", response)
        self.assertIn("FAILED (failures=1)", response)

    def test_does_not_fall_back_to_all_tests_when_none_are_related(self):
        executor = ResultExecutor()

        response = make_test_agent(StaticDiscovery(), executor).run_for_paths(("a.py",))

        self.assertIn("Durum: TEST BULUNAMADI", response)
        self.assertEqual(executor.commands, [])


class Architect:
    def plan(self, request):
        del request
        return ArchitecturePlan(
            summary="VALUE değerini güncelle.",
            existing_files=("a.py",),
            new_files=(),
            steps=(ArchitectureStep("Güncelle", "VALUE değerini değiştir.", ("a.py",)),),
            risks=(),
            tests=(),
            notes=(),
        )


class ProposalPreparer:
    def prepare_project_edit(self, request):
        del request
        return ProjectEditProposal(
            instruction="VALUE değerini 2 yap",
            edits=(
                EditProposal(
                    path="a.py",
                    updated_content="VALUE = 2\n",
                    expected_sha256="hash",
                    diff="-VALUE = 1\n+VALUE = 2",
                    original_character_count=10,
                    updated_character_count=10,
                ),
            ),
        )


class ProposalApplier:
    def apply_project_edit(self, proposal):
        del proposal
        return ProjectEditOutcome((EditOutcome("a.py", 10, 10),))


class RegressionRunner:
    def __init__(self):
        self.calls = []

    def run_for_paths(self, source_paths):
        self.calls.append(source_paths)
        return "TEST AGENT RAPORU\nDurum: BAŞARILI"


class CodingRegressionIntegrationTests(unittest.TestCase):
    def test_runs_regression_after_approved_coding_change(self):
        regression = RegressionRunner()
        coordinator = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(),
            architect=Architect(),
            proposal_preparer=ProposalPreparer(),
            proposal_applier=ProposalApplier(),
            regression_runner=regression,
        )
        coordinator.resolve("kodla: a.py içinde VALUE değerini 2 yap")

        response = coordinator.resolve("kod değişikliğini onayla")

        self.assertEqual(regression.calls, [("a.py",)])
        self.assertIn("TEST AGENT RAPORU", response or "")
        self.assertIn("Durum: BAŞARILI", response or "")


if __name__ == "__main__":
    unittest.main()
