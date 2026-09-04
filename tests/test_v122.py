import hashlib
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.models import ChatMessage
from boru.ollama_model import OllamaChatModel
from boru.tools import (
    BatchProjectEditApplier,
    JsonProjectPatchParser,
    LLMProjectEditProposalPreparer,
    LLMProjectFileSelector,
    ProjectCreateSpec,
    ProjectEditProposal,
    ProjectEditRequest,
    ProjectFileSelection,
    RuleBasedProjectEditRequestParser,
    SafeEditWorkspace,
    SafeProjectFileIndex,
    SafeWriteWorkspace,
    GroundedMultiPatchComposer,
    ProjectPatchSpec,
)
from boru.tools.edit_models import EditRequest
from boru.tools.project_selection import RuleFirstProjectFileSelector


class SequenceChatModel:
    def __init__(self, responses: Sequence[str]):
        self._responses = list(responses)

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        del messages
        if not self._responses:
            raise AssertionError("Beklenmeyen model çağrısı.")
        return self._responses.pop(0)


class FixedSelector:
    def __init__(self, paths: tuple[str, ...]):
        self._paths = paths

    def select_files(
        self,
        *,
        request,
        available_paths,
    ) -> ProjectFileSelection:
        del request
        del available_paths
        return ProjectFileSelection(self._paths)


class FailingSecondCreateWorkspace(SafeWriteWorkspace):
    def __init__(self, root: Path):
        super().__init__(root)
        self._writes = 0

    def write_text_file(self, relative_path: str, content: str):
        self._writes += 1
        if self._writes == 2:
            raise RuntimeError("simulated create failure")
        return super().write_text_file(relative_path, content)


class ProjectCreateTransactionTests(unittest.TestCase):
    def test_file_selector_uses_structured_output_schema(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_chat(**kwargs):
            calls.append(kwargs)
            return {"message": {"content": '{"paths":["controller.py"]}'}}

        selector = LLMProjectFileSelector(
            chat_model=OllamaChatModel("test", chat_client=fake_chat),
            max_attempts=1,
        )
        selection = selector.select_files(
            request=ProjectEditRequest("controller değişikliğini yap"),
            available_paths=("controller.py", "service.py"),
        )

        self.assertEqual(selection.paths, ("controller.py",))
        self.assertEqual(calls[0]["format"], selector._OUTPUT_SCHEMA)

    def test_grounded_patch_accepts_lf_model_text_for_crlf_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "controller.py"
            target.write_bytes(b'def run():\r\n    return "old"\r\n')
            source = SafeEditWorkspace(root).read_edit_source("controller.py")

            edits = GroundedMultiPatchComposer().compose(
                patches=(
                    ProjectPatchSpec(
                        "controller.py",
                        'def run():\n    return "old"\n',
                        'def run():\n    return "new"\n',
                    ),
                ),
                source_by_path={"controller.py": source},
            )

            self.assertEqual(
                edits[0].updated_content,
                'def run():\r\n    return "new"\r\n',
            )

    def test_create_request_keeps_new_paths_out_of_existing_file_selection(self) -> None:
        class UnexpectedFallback:
            def select_files(self, **kwargs):
                del kwargs
                raise AssertionError("Create isteği fallback'e gitmemeli.")

        selection = RuleFirstProjectFileSelector(
            fallback=UnexpectedFallback(),
            deterministic_min_paths=2,
        ).select_files(
            request=ProjectEditRequest(
                "controller.py dosyasını güncelle ve service.py oluştur"
            ),
            available_paths=("controller.py",),
        )

        self.assertEqual(selection.paths, ("controller.py",))

    def test_project_parser_accepts_create_action(self) -> None:
        request = RuleBasedProjectEditRequestParser().parse(
            "proje düzenle: services/user_service.py oluştur"
        )

        self.assertIsNotNone(request)

    def test_parser_accepts_patches_and_creates(self) -> None:
        plan = JsonProjectPatchParser().parse_plan(
            '{"patches":[{"path":"controller.py",'
            '"old_text":"old","new_text":"new","reason":"wire"}],'
            '"creates":[{"path":"service.py",'
            '"content":"class Service: pass\\n","reason":"new service"}]}'
        )

        self.assertEqual(len(plan.patches), 1)
        self.assertEqual(len(plan.creations), 1)
        self.assertEqual(plan.creations[0].path, "service.py")

    def test_legacy_patch_parser_result_stays_compatible(self) -> None:
        patches = JsonProjectPatchParser().parse(
            '{"patches":[{"path":"a.py","old_text":"a",'
            '"new_text":"b"}]}'
        )

        self.assertEqual(len(patches), 1)

    def test_preparer_builds_edit_and_create_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "controller.py").write_text("SERVICE = None\n", encoding="utf-8")
            edit_workspace = SafeEditWorkspace(root)
            create_workspace = SafeWriteWorkspace(root)
            model = SequenceChatModel(
                [
                    '{"patches":[{"path":"controller.py",'
                    '"old_text":"SERVICE = None","new_text":"SERVICE = Service()",'
                    '"reason":"wire service"}],'
                    '"creates":[{"path":"service.py",'
                    '"content":"class Service:\\n    pass\\n",'
                    '"reason":"new service"}]}'
                ]
            )

            proposal = LLMProjectEditProposalPreparer(
                chat_model=model,
                file_index=SafeProjectFileIndex(root),
                file_selector=FixedSelector(("controller.py",)),
                workspace=edit_workspace,
                creation_validator=create_workspace,
                max_attempts=1,
            ).prepare_project_edit(
                ProjectEditRequest("service oluştur ve controller'a bağla")
            )

            self.assertEqual(len(proposal.edits), 1)
            self.assertEqual(len(proposal.creations), 1)
            self.assertFalse((root / "service.py").exists())
            self.assertEqual(
                (root / "controller.py").read_text(encoding="utf-8"),
                "SERVICE = None\n",
            )

    def test_preparer_rejects_existing_create_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "controller.py").write_text("old\n", encoding="utf-8")
            (root / "service.py").write_text("existing\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "zaten mevcut"):
                LLMProjectEditProposalPreparer(
                    chat_model=SequenceChatModel(
                        [
                            '{"patches":[],"creates":[{"path":"service.py",'
                            '"content":"new","reason":"create"}]}'
                        ]
                    ),
                    file_index=SafeProjectFileIndex(root),
                    file_selector=FixedSelector(("controller.py",)),
                    workspace=SafeEditWorkspace(root),
                    creation_validator=SafeWriteWorkspace(root),
                    max_attempts=1,
                ).prepare_project_edit(ProjectEditRequest("service oluştur"))

    def test_proposal_rejects_edit_create_path_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("old", encoding="utf-8")
            workspace = SafeEditWorkspace(root)
            edit = workspace.prepare_exact_replacement(
                EditRequest("a.py", "old", "new")
            )

            with self.assertRaisesRegex(ValueError, "birden fazla"):
                ProjectEditProposal(
                    instruction="collision",
                    edits=(edit,),
                    creations=(ProjectCreateSpec("a.py", "content"),),
                )

    def test_transaction_applies_edit_and_create(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "controller.py").write_text("old\n", encoding="utf-8")
            edit_workspace = SafeEditWorkspace(root)
            create_workspace = SafeWriteWorkspace(root)
            edit = edit_workspace.prepare_exact_replacement(
                EditRequest("controller.py", "old", "new")
            )
            proposal = ProjectEditProposal(
                instruction="edit and create",
                edits=(edit,),
                creations=(ProjectCreateSpec("service.py", "service\n"),),
            )

            outcome = BatchProjectEditApplier(
                workspace=edit_workspace,
                creation_workspace=create_workspace,
            ).apply_project_edit(proposal)

            self.assertEqual(len(outcome.outcomes), 2)
            self.assertEqual(
                (root / "controller.py").read_text(encoding="utf-8"),
                "new\n",
            )
            self.assertEqual(
                (root / "service.py").read_text(encoding="utf-8"),
                "service\n",
            )

    def test_existing_create_target_blocks_all_edits_in_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "controller.py").write_text("old\n", encoding="utf-8")
            edit_workspace = SafeEditWorkspace(root)
            create_workspace = SafeWriteWorkspace(root)
            edit = edit_workspace.prepare_exact_replacement(
                EditRequest("controller.py", "old", "new")
            )
            proposal = ProjectEditProposal(
                instruction="stale create",
                edits=(edit,),
                creations=(ProjectCreateSpec("service.py", "planned\n"),),
            )
            (root / "service.py").write_text("external\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "zaten mevcut"):
                BatchProjectEditApplier(
                    workspace=edit_workspace,
                    creation_workspace=create_workspace,
                ).apply_project_edit(proposal)

            self.assertEqual(
                (root / "controller.py").read_text(encoding="utf-8"),
                "old\n",
            )
            self.assertEqual(
                (root / "service.py").read_text(encoding="utf-8"),
                "external\n",
            )

    def test_create_failure_rolls_back_edit_and_prior_create(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "controller.py").write_text("old\n", encoding="utf-8")
            edit_workspace = SafeEditWorkspace(root)
            create_workspace = FailingSecondCreateWorkspace(root)
            edit = edit_workspace.prepare_exact_replacement(
                EditRequest("controller.py", "old", "new")
            )
            proposal = ProjectEditProposal(
                instruction="rollback",
                edits=(edit,),
                creations=(
                    ProjectCreateSpec("service.py", "service\n"),
                    ProjectCreateSpec("test_service.py", "test\n"),
                ),
            )

            with self.assertRaisesRegex(RuntimeError, "geri alındı"):
                BatchProjectEditApplier(
                    workspace=edit_workspace,
                    creation_workspace=create_workspace,
                ).apply_project_edit(proposal)

            self.assertEqual(
                (root / "controller.py").read_text(encoding="utf-8"),
                "old\n",
            )
            self.assertFalse((root / "service.py").exists())
            self.assertFalse((root / "test_service.py").exists())

    def test_create_rollback_refuses_to_delete_changed_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = SafeWriteWorkspace(root)
            workspace.write_text_file("created.py", "planned\n")
            (root / "created.py").write_text("external\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "dışarıdan değişmiş"):
                workspace.remove_created_text_file(
                    "created.py",
                    expected_sha256=hashlib.sha256(b"planned\n").hexdigest(),
                )

            self.assertEqual(
                (root / "created.py").read_text(encoding="utf-8"),
                "external\n",
            )


if __name__ == "__main__":
    unittest.main()
