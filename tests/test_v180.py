import json
import tempfile
import unittest
from pathlib import Path

from boru.architecture import ArchitecturePlan, ArchitectureStep
from boru.coding import ControlledCodingCoordinator, RuleBasedCodingRequestParser
from boru.memory import ConservativeMemoryDecisionGate
from boru.tools import (
    EditOutcome,
    EditProposal,
    EditSource,
    BatchProjectEditApplier,
    LLMProjectEditProposalPreparer,
    ProjectEditOutcome,
    ProjectEditProposal,
    ProjectEditRequest,
    RuleBasedAssignmentEditProposalPreparer,
    RuleBasedSmartEditRequestParser,
    SafeEditWorkspace,
)


def architecture_plan() -> ArchitecturePlan:
    return ArchitecturePlan(
        summary="Ayar sabitini güvenli biçimde güncelle.",
        existing_files=("a.py",),
        new_files=(),
        steps=(
            ArchitectureStep(
                "Ayarı güncelle",
                "VALUE sabitini geriye uyumlu değiştir.",
                ("a.py",),
            ),
        ),
        risks=("Mevcut varsayılan değişir.",),
        tests=("VALUE kullanan davranışı doğrula.",),
        notes=(),
    )


def edit_proposal(path: str = "a.py") -> ProjectEditProposal:
    return ProjectEditProposal(
        instruction="VALUE değerini 2 yap",
        edits=(
            EditProposal(
                path=path,
                updated_content="VALUE = 2\n",
                expected_sha256="hash",
                diff="-VALUE = 1\n+VALUE = 2",
                original_character_count=10,
                updated_character_count=10,
            ),
        ),
    )


class Architect:
    def __init__(self):
        self.requests = []

    def plan(self, request):
        self.requests.append(request)
        return architecture_plan()


class Preparer:
    def __init__(self, proposal=None):
        self.proposal = proposal or edit_proposal()
        self.requests = []

    def prepare_project_edit(self, request):
        self.requests.append(request)
        return self.proposal


class Applier:
    def __init__(self):
        self.proposals = []

    def apply_project_edit(self, proposal):
        self.proposals.append(proposal)
        return ProjectEditOutcome((EditOutcome("a.py", 10, 10),))


def coordinator(*, proposal=None):
    architect = Architect()
    preparer = Preparer(proposal)
    applier = Applier()
    instance = ControlledCodingCoordinator(
        parser=RuleBasedCodingRequestParser(),
        architect=architect,
        proposal_preparer=preparer,
        proposal_applier=applier,
    )
    return instance, architect, preparer, applier


class CodingParserTests(unittest.TestCase):
    def test_parser_preserves_explicit_architecture_scope(self):
        request = RuleBasedCodingRequestParser().parse(
            "kodla: a.py içinde yeni ayarı yalnızca bu dosyada uygula"
        )
        self.assertEqual(request.architecture_request.file_scope, ("a.py",))

    def test_coding_request_is_not_memory_candidate(self):
        self.assertFalse(
            ConservativeMemoryDecisionGate().should_evaluate(
                "kodla: a.py içinde VALUE değerini güncelle"
            )
        )


class CodingCoordinatorTests(unittest.TestCase):
    def test_stages_architect_scoped_diff_without_applying(self):
        instance, architect, preparer, applier = coordinator()

        response = instance.resolve(
            "kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap"
        )

        self.assertIn("CODING AGENT ÖNERİSİ", response or "")
        self.assertIn("-VALUE = 1", response or "")
        self.assertTrue(instance.has_pending)
        self.assertEqual(len(architect.requests), 1)
        self.assertEqual(preparer.requests[0].existing_file_scope, ("a.py",))
        self.assertEqual(preparer.requests[0].new_file_scope, ())
        self.assertEqual(applier.proposals, [])

    def test_requires_exact_approval_then_applies(self):
        instance, _, _, applier = coordinator()
        instance.resolve("kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap")

        pending = instance.resolve("onayla")
        self.assertIn("kod değişikliğini onayla", pending or "")
        self.assertEqual(applier.proposals, [])

        result = instance.resolve("kod değişikliğini onayla")
        self.assertIn("Coding Agent değişikliği uygulandı", result or "")
        self.assertEqual(len(applier.proposals), 1)
        self.assertFalse(instance.has_pending)

    def test_cancel_drops_proposal(self):
        instance, _, _, applier = coordinator()
        instance.resolve("kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap")

        result = instance.resolve("iptal")

        self.assertIn("hiçbir dosya değiştirilmedi", result or "")
        self.assertEqual(applier.proposals, [])
        self.assertFalse(instance.has_pending)

    def test_rejects_proposal_outside_architect_scope(self):
        instance, _, _, applier = coordinator(proposal=edit_proposal("outside.py"))

        result = instance.resolve(
            "kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap"
        )

        self.assertIn("Architect kapsamı dışına çıktı", result or "")
        self.assertEqual(applier.proposals, [])
        self.assertFalse(instance.has_pending)


class Model:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_structured(self, messages, schema):
        del schema
        self.calls.append(messages)
        return json.dumps(self.payload)


class Index:
    def list_editable_files(self):
        return ("a.py", "outside.py")


class Selector:
    def select_files(self, *, request, available_paths):
        raise AssertionError((request, available_paths))


class Workspace:
    def read_edit_source(self, path):
        if path != "a.py":
            raise AssertionError(path)
        return EditSource("a.py", "VALUE = 1\n", "hash")


class CreationValidator:
    def __init__(self):
        self.paths = []

    def validate_new_text_file(self, relative_path, content):
        self.paths.append((relative_path, content))


class ScopedProjectEditTests(unittest.TestCase):
    def test_architect_scope_bypasses_selector_and_is_in_prompt(self):
        model = Model({
            "patches": [{
                "path": "a.py",
                "old_text": "VALUE = 1",
                "new_text": "VALUE = 2",
                "reason": "Ayarı güncelle",
            }],
            "creates": [],
        })
        preparer = LLMProjectEditProposalPreparer(
            chat_model=model,
            file_index=Index(),
            file_selector=Selector(),
            workspace=Workspace(),
            creation_validator=CreationValidator(),
            max_attempts=1,
        )

        proposal = preparer.prepare_project_edit(
            ProjectEditRequest("VALUE değerini 2 yap", ("a.py",), ())
        )

        self.assertEqual(proposal.edits[0].path, "a.py")
        prompt = model.calls[0][1].content
        self.assertIn("ALLOWED_NEW_FILES:\n- yok", prompt)

    def test_create_outside_architect_scope_is_rejected(self):
        model = Model({
            "patches": [],
            "creates": [{
                "path": "outside.py",
                "content": "VALUE = 2\n",
                "reason": "Yeni dosya",
            }],
        })
        preparer = LLMProjectEditProposalPreparer(
            chat_model=model,
            file_index=Index(),
            file_selector=Selector(),
            workspace=Workspace(),
            creation_validator=CreationValidator(),
            max_attempts=1,
        )

        with self.assertRaisesRegex(ValueError, "Architect dosya kapsamı"):
            preparer.prepare_project_edit(
                ProjectEditRequest("VALUE değerini 2 yap", ("a.py",), ())
            )

    def test_architect_can_scope_a_creation_only_transaction(self):
        model = Model({
            "patches": [],
            "creates": [{
                "path": "new_service.py",
                "content": "VALUE = 2\n",
                "reason": "Yeni servis",
            }],
        })
        validator = CreationValidator()
        preparer = LLMProjectEditProposalPreparer(
            chat_model=model,
            file_index=Index(),
            file_selector=Selector(),
            workspace=Workspace(),
            creation_validator=validator,
            max_attempts=1,
        )

        proposal = preparer.prepare_project_edit(
            ProjectEditRequest("servisi oluştur", (), ("new_service.py",))
        )

        self.assertEqual(proposal.creations[0].path, "new_service.py")
        self.assertEqual(validator.paths, [("new_service.py", "VALUE = 2\n")])


class WorkspacePreparer:
    def __init__(self, workspace):
        self.workspace = workspace

    def prepare_project_edit(self, request):
        if request.existing_file_scope != ("a.py",):
            raise AssertionError(request.existing_file_scope)
        source = self.workspace.read_edit_source("a.py")
        return ProjectEditProposal(
            instruction=request.instruction,
            edits=(
                EditProposal(
                    path="a.py",
                    updated_content="VALUE = 2\n",
                    expected_sha256=source.sha256,
                    diff="-VALUE = 1\n+VALUE = 2",
                    original_character_count=len(source.content),
                    updated_character_count=10,
                ),
            ),
        )


class CodingWorkspaceIntegrationTests(unittest.TestCase):
    @staticmethod
    def _coordinator(root):
        workspace = SafeEditWorkspace(root)
        return ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(),
            architect=Architect(),
            proposal_preparer=WorkspacePreparer(workspace),
            proposal_applier=BatchProjectEditApplier(workspace=workspace),
        )

    def test_approval_applies_grounded_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            instance = self._coordinator(directory)

            instance.resolve(
                "kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap"
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 1\n")

            result = instance.resolve("kod değişikliğini onayla")

            self.assertIn("Coding Agent değişikliği uygulandı", result or "")
            self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 2\n")

    def test_stale_source_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            instance = self._coordinator(directory)
            instance.resolve(
                "kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap"
            )
            target.write_text("VALUE = 99\n", encoding="utf-8")

            result = instance.resolve("kod değişikliğini onayla")

            self.assertIn("önizlemeden sonra değişmiş", result or "")
            self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 99\n")

    def test_simple_assignment_uses_deterministic_edit_before_llm(self):
        class UnexpectedPreparer:
            def prepare_project_edit(self, request):
                raise AssertionError(request)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            workspace = SafeEditWorkspace(directory)
            instance = ControlledCodingCoordinator(
                parser=RuleBasedCodingRequestParser(),
                architect=Architect(),
                proposal_preparer=UnexpectedPreparer(),
                proposal_applier=BatchProjectEditApplier(workspace=workspace),
                deterministic_edit_parser=RuleBasedSmartEditRequestParser(),
                deterministic_edit_preparer=RuleBasedAssignmentEditProposalPreparer(
                    workspace=workspace
                ),
            )

            preview = instance.resolve(
                "kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap"
            )

            self.assertIn("-VALUE = 1", preview or "")
            self.assertIn("+VALUE = 2", preview or "")
            self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 1\n")

            instance.resolve("kod değişikliğini onayla")
            self.assertEqual(target.read_text(encoding="utf-8"), "VALUE = 2\n")

    def test_single_file_fast_architecture_scope_never_calls_selector(self):
        class UnexpectedModel:
            def generate_structured(self, messages, schema):
                raise AssertionError((messages, schema))

        class UnexpectedPreparer:
            def prepare_project_edit(self, request):
                raise AssertionError(request)

        class OneFileIndex:
            def list_editable_files(self):
                return ("a.py", "outside.py")

        class UnexpectedSelector:
            def select_files(self, *, request, available_paths):
                raise AssertionError((request, available_paths))

        from boru.architecture import LLMArchitectAgent

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            workspace = SafeEditWorkspace(directory)
            architect = LLMArchitectAgent(
                chat_model=UnexpectedModel(),
                file_index=OneFileIndex(),
                file_selector=UnexpectedSelector(),
                workspace=workspace,
                creation_validator=CreationValidator(),
                fast_scoped_plans=True,
            )
            instance = ControlledCodingCoordinator(
                parser=RuleBasedCodingRequestParser(),
                architect=architect,
                proposal_preparer=UnexpectedPreparer(),
                proposal_applier=BatchProjectEditApplier(workspace=workspace),
                deterministic_edit_parser=RuleBasedSmartEditRequestParser(),
                deterministic_edit_preparer=RuleBasedAssignmentEditProposalPreparer(
                    workspace=workspace
                ),
            )

            response = instance.resolve(
                "kodla: a.py içinde VALUE değerini yalnızca bu dosyada 2 yap"
            )

            self.assertIn("CODING AGENT ÖNERİSİ", response or "")


if __name__ == "__main__":
    unittest.main()
