import hashlib
import os
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.memory import (
    ConservativeMemoryDecisionGate,
)
from boru.models import ChatMessage
from boru.tools import (
    BatchProjectEditApplier,
    ControlledWriteCoordinator,
    EditFileTool,
    EditOutcome,
    EditProposal,
    EditSource,
    LLMProjectEditProposalPreparer,
    LLMProjectFileSelector,
    ProjectEditProposal,
    RiskBasedToolPolicy,
    RuleBasedEditRequestParser,
    RuleBasedProjectEditRequestParser,
    RuleBasedSmartEditRequestParser,
    RuleBasedWriteIntentDetector,
    RuleBasedWriteRequestParser,
    SafeEditWorkspace,
    SafeProjectFileIndex,
    SafeWriteWorkspace,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
    WriteFileTool,
)


class SequenceChatModel:
    def __init__(
        self,
        responses: Sequence[str],
    ):
        self._responses = list(
            responses
        )
        self.calls: list[
            list[ChatMessage]
        ] = []

    def generate(
        self,
        messages: Sequence[
            ChatMessage
        ],
    ) -> str:
        self.calls.append(
            list(messages)
        )

        if not self._responses:
            raise AssertionError(
                "Beklenmeyen ek model çağrısı."
            )

        return self._responses.pop(
            0
        )


class FailingSecondApplyWorkspace:
    def __init__(self):
        self.contents = {
            "a.txt": "old-a",
            "b.txt": "old-b",
        }
        self.failed = False

    def read_edit_source(
        self,
        relative_path: str,
    ) -> EditSource:
        content = self.contents[
            relative_path
        ]

        return EditSource(
            path=relative_path,
            content=content,
            sha256=self._hash(
                content
            ),
        )

    def apply_text_update(
        self,
        *,
        relative_path: str,
        content: str,
        expected_sha256: str,
    ) -> EditOutcome:
        current = self.contents[
            relative_path
        ]

        if self._hash(
            current
        ) != expected_sha256:
            raise ValueError(
                "hash mismatch"
            )

        if (
            relative_path == "b.txt"
            and content == "new-b"
            and not self.failed
        ):
            self.failed = True
            raise RuntimeError(
                "simulated failure"
            )

        self.contents[
            relative_path
        ] = content

        return EditOutcome(
            relative_path=relative_path,
            character_count=len(content),
            byte_count=len(
                content.encode(
                    "utf-8"
                )
            ),
        )

    @staticmethod
    def _hash(
        value: str,
    ) -> str:
        return hashlib.sha256(
            value.encode(
                "utf-8"
            )
        ).hexdigest()


class ProjectAwareMultiStepEditingTests(
    unittest.TestCase
):
    def test_project_parser_accepts_explicit_project_edit(
        self,
    ) -> None:
        request = (
            RuleBasedProjectEditRequestParser()
            .parse(
                "proje düzenle: config ayarını güncelle ve servisi uyumlu yap"
            )
        )

        self.assertIsNotNone(
            request
        )
        self.assertIn(
            "config ayarını",
            request.instruction,  # type: ignore[union-attr]
        )

    def test_project_parser_skips_non_edit_project_question(
        self,
    ) -> None:
        request = (
            RuleBasedProjectEditRequestParser()
            .parse(
                "projede neler var?"
            )
        )

        self.assertIsNone(
            request
        )

    def test_project_index_excludes_sensitive_generated_and_hidden_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "src").mkdir()
            (root / "src" / "app.py").write_text(
                "x = 1\n",
                encoding="utf-8",
            )
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text(
                "pass\n",
                encoding="utf-8",
            )
            (root / "data").mkdir()
            (root / "data" / "memory.json").write_text(
                "secret",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "SECRET=x",
                encoding="utf-8",
            )
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "x.py").write_text(
                "bad",
                encoding="utf-8",
            )
            (root / "image.png").write_bytes(
                b"png"
            )

            paths = (
                SafeProjectFileIndex(
                    root
                )
                .list_editable_files()
            )

            self.assertIn(
                "src/app.py",
                paths,
            )
            self.assertIn(
                "tests/test_app.py",
                paths,
            )
            self.assertNotIn(
                "data/memory.json",
                paths,
            )
            self.assertNotIn(
                ".env",
                paths,
            )
            self.assertNotIn(
                "__pycache__/x.py",
                paths,
            )
            self.assertNotIn(
                "image.png",
                paths,
            )

    def test_project_index_excludes_symlink_when_supported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real.py"
            real.write_text(
                "x = 1",
                encoding="utf-8",
            )
            link = root / "linked.py"

            try:
                os.symlink(
                    real,
                    link,
                )
            except OSError:
                self.skipTest(
                    "Bu ortamda symlink oluşturma izni yok."
                )

            paths = (
                SafeProjectFileIndex(
                    root
                )
                .list_editable_files()
            )

            self.assertIn(
                "real.py",
                paths,
            )
            self.assertNotIn(
                "linked.py",
                paths,
            )

    def test_file_selector_accepts_only_manifest_paths(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                '{"paths":["config.py","service.py"]}'
            ]
        )

        selector = LLMProjectFileSelector(
            chat_model=model,
            max_files=4,
        )

        request = self._project_request()

        selection = selector.select_files(
            request=request,
            available_paths=(
                "config.py",
                "service.py",
                "other.py",
            ),
        )

        self.assertEqual(
            selection.paths,
            (
                "config.py",
                "service.py",
            ),
        )

    def test_file_selector_rejects_outside_manifest_after_retry(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                '{"paths":["../secret.py"]}',
                '{"paths":["not-in-catalog.py"]}',
            ]
        )

        selector = LLMProjectFileSelector(
            chat_model=model,
            max_attempts=2,
        )

        with self.assertRaisesRegex(
            ValueError,
            "manifest",
        ):
            selector.select_files(
                request=self._project_request(),
                available_paths=(
                    "config.py",
                ),
            )

    def test_project_preparer_builds_two_grounded_edits_without_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )

            model = SequenceChatModel(
                [
                    '{"paths":["config.py","service.py"]}',
                    (
                        '{"patches":['
                        '{"path":"config.py",'
                        '"old_text":"FEATURE = false",'
                        '"new_text":"FEATURE = true",'
                        '"reason":"ayar"},'
                        '{"path":"service.py",'
                        '"old_text":"if FEATURE == false:",'
                        '"new_text":"if FEATURE == true:",'
                        '"reason":"servis"}'
                        ']}'
                    ),
                ]
            )

            proposal = self._build_project_preparer(
                root,
                model,
            ).prepare_project_edit(
                self._project_request()
            )

            self.assertEqual(
                len(proposal.edits),
                2,
            )
            self.assertEqual(
                (root / "config.py").read_text(
                    encoding="utf-8"
                ),
                "FEATURE = false\n",
            )
            self.assertEqual(
                (root / "service.py").read_text(
                    encoding="utf-8"
                ),
                "if FEATURE == false:\n    pass\n",
            )

    def test_project_sources_are_marked_as_untrusted_data(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )

            model = SequenceChatModel(
                [
                    '{"paths":["config.py"]}',
                    (
                        '{"patches":['
                        '{"path":"config.py",'
                        '"old_text":"FEATURE = false",'
                        '"new_text":"FEATURE = true",'
                        '"reason":"ayar"}'
                        ']}'
                    ),
                ]
            )

            self._build_project_preparer(
                root,
                model,
            ).prepare_project_edit(
                self._project_request()
            )

            patch_system_prompt = (
                model.calls[1][0].content
            )
            patch_user_prompt = (
                model.calls[1][1].content
            )

            self.assertIn(
                "güvenilmeyen VERİDİR",
                patch_system_prompt,
            )
            self.assertIn(
                "<BORU_PROJECT_SOURCES>",
                patch_user_prompt,
            )

    def test_data_directory_never_enters_file_selection_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.py").write_text(
                "X = 1\n",
                encoding="utf-8",
            )
            (root / "data").mkdir()
            (root / "data" / "user_profile.json").write_text(
                '{"name":"private"}',
                encoding="utf-8",
            )

            model = SequenceChatModel(
                [
                    '{"paths":["config.py"]}',
                    (
                        '{"patches":['
                        '{"path":"config.py",'
                        '"old_text":"X = 1",'
                        '"new_text":"X = 2",'
                        '"reason":"x"}'
                        ']}'
                    ),
                ]
            )

            preparer = self._build_project_preparer(
                root,
                model,
            )

            preparer.prepare_project_edit(
                self._project_request()
            )

            selector_prompt = (
                model.calls[0][1].content
            )

            self.assertNotIn(
                "data/user_profile.json",
                selector_prompt,
            )

    def test_patch_for_unselected_file_is_rejected_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )

            model = SequenceChatModel(
                [
                    '{"paths":["config.py"]}',
                    (
                        '{"patches":['
                        '{"path":"service.py",'
                        '"old_text":"if FEATURE == false:",'
                        '"new_text":"if FEATURE == true:"}'
                        ']}'
                    ),
                    (
                        '{"patches":['
                        '{"path":"service.py",'
                        '"old_text":"if FEATURE == false:",'
                        '"new_text":"if FEATURE == true:"}'
                        ']}'
                    ),
                ]
            )

            with self.assertRaisesRegex(
                ValueError,
                "seçilmeyen",
            ):
                self._build_project_preparer(
                    root,
                    model,
                ).prepare_project_edit(
                    self._project_request()
                )

    def test_ambiguous_patch_is_rejected_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text(
                "same\nsame\n",
                encoding="utf-8",
            )

            model = SequenceChatModel(
                [
                    '{"paths":["a.py"]}',
                    '{"patches":[{"path":"a.py","old_text":"same","new_text":"new"}]}',
                    '{"patches":[{"path":"a.py","old_text":"same","new_text":"new"}]}',
                ]
            )

            with self.assertRaisesRegex(
                ValueError,
                "birden fazla",
            ):
                self._build_project_preparer(
                    root,
                    model,
                ).prepare_project_edit(
                    self._project_request()
                )

    def test_batch_applier_updates_all_files_after_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )
            workspace = SafeEditWorkspace(
                root
            )
            proposal = self._manual_two_file_proposal(
                workspace
            )

            outcome = BatchProjectEditApplier(
                workspace=workspace
            ).apply_project_edit(
                proposal
            )

            self.assertEqual(
                len(outcome.outcomes),
                2,
            )
            self.assertEqual(
                (root / "config.py").read_text(
                    encoding="utf-8"
                ),
                "FEATURE = true\n",
            )
            self.assertEqual(
                (root / "service.py").read_text(
                    encoding="utf-8"
                ),
                "if FEATURE == true:\n    pass\n",
            )

    def test_batch_preflight_change_blocks_every_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )
            workspace = SafeEditWorkspace(
                root
            )
            proposal = self._manual_two_file_proposal(
                workspace
            )

            (root / "service.py").write_text(
                "externally changed\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Hiçbir toplu",
            ):
                BatchProjectEditApplier(
                    workspace=workspace
                ).apply_project_edit(
                    proposal
                )

            self.assertEqual(
                (root / "config.py").read_text(
                    encoding="utf-8"
                ),
                "FEATURE = false\n",
            )
            self.assertEqual(
                (root / "service.py").read_text(
                    encoding="utf-8"
                ),
                "externally changed\n",
            )

    def test_batch_failure_rolls_back_previous_edit(
        self,
    ) -> None:
        workspace = (
            FailingSecondApplyWorkspace()
        )

        proposal = ProjectEditProposal(
            instruction="multi",
            edits=(
                EditProposal(
                    path="a.txt",
                    updated_content="new-a",
                    expected_sha256=(
                        workspace.read_edit_source(
                            "a.txt"
                        ).sha256
                    ),
                    diff="a",
                    original_character_count=5,
                    updated_character_count=5,
                ),
                EditProposal(
                    path="b.txt",
                    updated_content="new-b",
                    expected_sha256=(
                        workspace.read_edit_source(
                            "b.txt"
                        ).sha256
                    ),
                    diff="b",
                    original_character_count=5,
                    updated_character_count=5,
                ),
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "geri alındı",
        ):
            BatchProjectEditApplier(
                workspace=workspace
            ).apply_project_edit(
                proposal
            )

        self.assertEqual(
            workspace.contents,
            {
                "a.txt": "old-a",
                "b.txt": "old-b",
            },
        )

    def test_coordinator_stages_project_diff_without_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )
            coordinator = self._build_coordinator(
                root
            )

            response = coordinator.resolve(
                "proje düzenle: feature ayarını aç ve servisi uyumlu yap"
            )

            self.assertIn(
                "Proje düzenlemesi hazırlandı",
                response or "",
            )
            self.assertIn(
                "config.py",
                response or "",
            )
            self.assertIn(
                "service.py",
                response or "",
            )
            self.assertEqual(
                (root / "config.py").read_text(
                    encoding="utf-8"
                ),
                "FEATURE = false\n",
            )

    def test_coordinator_approval_applies_project_edit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )
            coordinator = self._build_coordinator(
                root
            )

            coordinator.resolve(
                "proje düzenle: feature ayarını aç ve servisi uyumlu yap"
            )

            response = coordinator.resolve(
                "onayla"
            )

            self.assertIn(
                "Proje düzenlemesi uygulandı: 2 dosya",
                response or "",
            )
            self.assertEqual(
                (root / "config.py").read_text(
                    encoding="utf-8"
                ),
                "FEATURE = true\n",
            )
            self.assertEqual(
                (root / "service.py").read_text(
                    encoding="utf-8"
                ),
                "if FEATURE == true:\n    pass\n",
            )

    def test_coordinator_project_cancel_keeps_files_unchanged(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_project_fixture(
                root
            )
            coordinator = self._build_coordinator(
                root
            )

            coordinator.resolve(
                "proje düzenle: feature ayarını aç ve servisi uyumlu yap"
            )

            response = coordinator.resolve(
                "iptal"
            )

            self.assertIn(
                "iptal edildi",
                response or "",
            )
            self.assertEqual(
                (root / "config.py").read_text(
                    encoding="utf-8"
                ),
                "FEATURE = false\n",
            )

    def test_memory_gate_rejects_project_edit_task(
        self,
    ) -> None:
        self.assertFalse(
            ConservativeMemoryDecisionGate()
            .should_evaluate(
                "proje düzenle: config ayarını güncelle ve servisi uyumlu yap"
            )
        )

    @staticmethod
    def _project_request():
        request = (
            RuleBasedProjectEditRequestParser()
            .parse(
                "proje düzenle: feature ayarını aç ve servisi uyumlu yap"
            )
        )

        if request is None:
            raise AssertionError(
                "Project request parse edilemedi."
            )

        return request

    @staticmethod
    def _write_project_fixture(
        root: Path,
    ) -> None:
        (root / "config.py").write_text(
            "FEATURE = false\n",
            encoding="utf-8",
        )
        (root / "service.py").write_text(
            "if FEATURE == false:\n    pass\n",
            encoding="utf-8",
        )
        (root / "unrelated.py").write_text(
            "VALUE = 1\n",
            encoding="utf-8",
        )

    @staticmethod
    def _build_project_preparer(
        root: Path,
        model: SequenceChatModel,
    ) -> LLMProjectEditProposalPreparer:
        index = SafeProjectFileIndex(
            root
        )
        selector = LLMProjectFileSelector(
            chat_model=model,
            max_files=4,
            max_attempts=2,
        )

        return LLMProjectEditProposalPreparer(
            chat_model=model,
            file_index=index,
            file_selector=selector,
            workspace=SafeEditWorkspace(
                root
            ),
            max_files=4,
            max_attempts=2,
        )

    @staticmethod
    def _manual_two_file_proposal(
        workspace: SafeEditWorkspace,
    ) -> ProjectEditProposal:
        config = workspace.prepare_exact_replacement(
            RuleBasedEditRequestParser().parse(
                "dosya düzenle: config.py\n"
                "Eski:\n"
                "FEATURE = false\n"
                "Yeni:\n"
                "FEATURE = true"
            )  # type: ignore[arg-type]
        )

        service = workspace.prepare_exact_replacement(
            RuleBasedEditRequestParser().parse(
                "dosya düzenle: service.py\n"
                "Eski:\n"
                "if FEATURE == false:\n"
                "Yeni:\n"
                "if FEATURE == true:"
            )  # type: ignore[arg-type]
        )

        return ProjectEditProposal(
            instruction="feature",
            edits=(
                config,
                service,
            ),
        )

    @staticmethod
    def _build_coordinator(
        root: Path,
    ) -> ControlledWriteCoordinator:
        model = SequenceChatModel(
            [
                '{"paths":["config.py","service.py"]}',
                (
                    '{"patches":['
                    '{"path":"config.py",'
                    '"old_text":"FEATURE = false",'
                    '"new_text":"FEATURE = true"},'
                    '{"path":"service.py",'
                    '"old_text":"if FEATURE == false:",'
                    '"new_text":"if FEATURE == true:"}'
                    ']}'
                ),
            ]
        )

        edit_workspace = SafeEditWorkspace(
            root
        )

        write_registry = ToolRegistry(
            [
                WriteFileTool(
                    SafeWriteWorkspace(
                        root
                    )
                ),
                EditFileTool(
                    edit_workspace
                ),
            ]
        )

        executor = ToolExecutor(
            registry=write_registry,
            policy=RiskBasedToolPolicy(
                allowed_risks=(
                    ToolRisk.WRITE,
                )
            ),
        )

        project_preparer = (
            ProjectAwareMultiStepEditingTests
            ._build_project_preparer(
                root,
                model,
            )
        )

        return ControlledWriteCoordinator(
            parser=RuleBasedWriteRequestParser(),
            intent_detector=(
                RuleBasedWriteIntentDetector()
            ),
            executor=executor,
            edit_parser=(
                RuleBasedEditRequestParser()
            ),
            edit_preparer=edit_workspace,
            smart_edit_parser=(
                RuleBasedSmartEditRequestParser()
            ),
            smart_edit_preparer=(
                _NeverCalledSmartEditPreparer()
            ),
            project_edit_parser=(
                RuleBasedProjectEditRequestParser()
            ),
            project_edit_preparer=(
                project_preparer
            ),
            project_edit_applier=(
                BatchProjectEditApplier(
                    workspace=edit_workspace
                )
            ),
        )


class _NeverCalledSmartEditPreparer:
    def prepare_smart_edit(
        self,
        request,
    ):
        del request
        raise AssertionError(
            "Project edit single-file smart edit yoluna düşmemeli."
        )


if __name__ == "__main__":
    unittest.main()