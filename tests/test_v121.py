import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.models import ChatMessage
from boru.ollama_model import OllamaChatModel
from boru.tools import (
    BatchProjectEditApplier,
    DependencyAwareProjectFileSelector,
    GroundedMultiPatchComposer,
    LLMProjectEditProposalPreparer,
    ProjectEditRequest,
    ProjectFileSelection,
    ProjectPatchSpec,
    SafeEditWorkspace,
    SafeProjectFileIndex,
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


class FixedSelector:
    def __init__(
        self,
        paths: tuple[str, ...],
    ):
        self.paths = paths
        self.calls = 0

    def select_files(
        self,
        *,
        request,
        available_paths,
    ) -> ProjectFileSelection:
        del request
        del available_paths

        self.calls += 1

        return ProjectFileSelection(
            paths=self.paths
        )


class MultiPatchAndDependencyAwareTests(
    unittest.TestCase
):
    def test_two_patches_same_file_become_one_edit_proposal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "config.py"
            ).write_bytes(
                b"MAX_RETRY = 1\n"
                b"TIMEOUT = 5\n"
            )

            workspace = (
                SafeEditWorkspace(
                    root
                )
            )

            source = (
                workspace
                .read_edit_source(
                    "config.py"
                )
            )

            edits = (
                GroundedMultiPatchComposer()
                .compose(
                    patches=(
                        ProjectPatchSpec(
                            path="config.py",
                            old_text=(
                                "MAX_RETRY = 1"
                            ),
                            new_text=(
                                "MAX_RETRY = 3"
                            ),
                        ),
                        ProjectPatchSpec(
                            path="config.py",
                            old_text=(
                                "TIMEOUT = 5"
                            ),
                            new_text=(
                                "TIMEOUT = 10"
                            ),
                        ),
                    ),
                    source_by_path={
                        "config.py": source,
                    },
                )
            )

            self.assertEqual(
                len(edits),
                1,
            )

            self.assertEqual(
                edits[
                    0
                ].updated_content,
                (
                    "MAX_RETRY = 3\n"
                    "TIMEOUT = 10\n"
                ),
            )

            self.assertIn(
                "-MAX_RETRY = 1",
                edits[0].diff,
            )

            self.assertIn(
                "+TIMEOUT = 10",
                edits[0].diff,
            )

    def test_multi_patch_composer_does_not_write_before_approval(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            target = (
                root
                / "a.py"
            )

            target.write_bytes(
                b"A = 1\n"
                b"B = 2\n"
            )

            workspace = (
                SafeEditWorkspace(
                    root
                )
            )

            source = (
                workspace
                .read_edit_source(
                    "a.py"
                )
            )

            GroundedMultiPatchComposer().compose(
                patches=(
                    ProjectPatchSpec(
                        "a.py",
                        "A = 1",
                        "A = 10",
                    ),
                    ProjectPatchSpec(
                        "a.py",
                        "B = 2",
                        "B = 20",
                    ),
                ),
                source_by_path={
                    "a.py": source,
                },
            )

            self.assertEqual(
                target.read_bytes(),
                (
                    b"A = 1\n"
                    b"B = 2\n"
                ),
            )

    def test_overlapping_patches_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "a.txt"
            ).write_bytes(
                b"abcdef"
            )

            source = (
                SafeEditWorkspace(
                    root
                )
                .read_edit_source(
                    "a.txt"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "çakış",
            ):
                GroundedMultiPatchComposer().compose(
                    patches=(
                        ProjectPatchSpec(
                            "a.txt",
                            "abcd",
                            "X",
                        ),
                        ProjectPatchSpec(
                            "a.txt",
                            "cdef",
                            "Y",
                        ),
                    ),
                    source_by_path={
                        "a.txt": source,
                    },
                )

    def test_ambiguous_old_text_is_rejected_per_patch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "a.txt"
            ).write_bytes(
                b"same\n"
                b"same\n"
            )

            source = (
                SafeEditWorkspace(
                    root
                )
                .read_edit_source(
                    "a.txt"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "birden fazla",
            ):
                GroundedMultiPatchComposer().compose(
                    patches=(
                        ProjectPatchSpec(
                            "a.txt",
                            "same",
                            "new",
                        ),
                    ),
                    source_by_path={
                        "a.txt": source,
                    },
                )

    def test_per_file_patch_limit_is_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "a.txt"
            ).write_bytes(
                b"A\n"
                b"B\n"
                b"C\n"
            )

            source = (
                SafeEditWorkspace(
                    root
                )
                .read_edit_source(
                    "a.txt"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "en fazla 2 patch",
            ):
                GroundedMultiPatchComposer(
                    max_patches_per_file=2
                ).compose(
                    patches=(
                        ProjectPatchSpec(
                            "a.txt",
                            "A",
                            "1",
                        ),
                        ProjectPatchSpec(
                            "a.txt",
                            "B",
                            "2",
                        ),
                        ProjectPatchSpec(
                            "a.txt",
                            "C",
                            "3",
                        ),
                    ),
                    source_by_path={
                        "a.txt": source,
                    },
                )

    def test_llm_project_preparer_accepts_multiple_patches_for_one_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "service.py"
            ).write_bytes(
                b"MAX_RETRY = 1\n"
                b"\n"
                b"def run():\n"
                b"    return MAX_RETRY\n"
            )

            model = (
                SequenceChatModel(
                    [
                        (
                            '{"patches":['
                            '{"path":"service.py",'
                            '"old_text":"MAX_RETRY = 1",'
                            '"new_text":"MAX_RETRY = 3"},'
                            '{"path":"service.py",'
                            '"old_text":"return MAX_RETRY",'
                            '"new_text":"return max(1, MAX_RETRY)"}'
                            ']}'
                        )
                    ]
                )
            )

            preparer = (
                LLMProjectEditProposalPreparer(
                    chat_model=model,
                    file_index=(
                        SafeProjectFileIndex(
                            root
                        )
                    ),
                    file_selector=(
                        FixedSelector(
                            (
                                "service.py",
                            )
                        )
                    ),
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                    max_attempts=1,
                )
            )

            proposal = (
                preparer
                .prepare_project_edit(
                    ProjectEditRequest(
                        "service.py içindeki retry ayarını "
                        "güncelle ve kullanımı güvenli yap"
                    )
                )
            )

            self.assertEqual(
                len(
                    proposal.edits
                ),
                1,
            )

            self.assertIn(
                "MAX_RETRY = 3",
                proposal.edits[
                    0
                ].updated_content,
            )

            self.assertIn(
                "return max(1, MAX_RETRY)",
                proposal.edits[
                    0
                ].updated_content,
            )

    def test_project_preparer_uses_ollama_structured_output_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "config.py"
            ).write_bytes(
                b"RETRY = 1\n"
            )

            calls: list[
                dict[str, object]
            ] = []

            def fake_chat(
                **kwargs,
            ):
                calls.append(
                    kwargs
                )

                return {
                    "message": {
                        "content": (
                            '{"patches":['
                            '{"path":"config.py",'
                            '"old_text":"RETRY = 1",'
                            '"new_text":"RETRY = 3",'
                            '"reason":"retry update"}'
                            ']}'
                        )
                    }
                }

            preparer = (
                LLMProjectEditProposalPreparer(
                    chat_model=(
                        OllamaChatModel(
                            "test-model",
                            chat_client=(
                                fake_chat
                            ),
                        )
                    ),
                    file_index=(
                        SafeProjectFileIndex(
                            root
                        )
                    ),
                    file_selector=(
                        FixedSelector(
                            (
                                "config.py",
                            )
                        )
                    ),
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                    max_attempts=1,
                )
            )

            proposal = (
                preparer
                .prepare_project_edit(
                    ProjectEditRequest(
                        "config.py retry değerini güncelle"
                    )
                )
            )

            self.assertEqual(
                len(
                    proposal.edits
                ),
                1,
            )

            self.assertEqual(
                calls[0][
                    "format"
                ],
                preparer._OUTPUT_SCHEMA,
            )

    def test_normal_ollama_generation_does_not_force_json_format(
        self,
    ) -> None:
        calls: list[
            dict[str, object]
        ] = []

        def fake_chat(
            **kwargs,
        ):
            calls.append(
                kwargs
            )

            return {
                "message": {
                    "content": "Merhaba",
                }
            }

        answer = (
            OllamaChatModel(
                "test-model",
                chat_client=(
                    fake_chat
                ),
            )
            .generate(
                [
                    ChatMessage(
                        role="user",
                        content="Merhaba",
                    )
                ]
            )
        )

        self.assertEqual(
            answer,
            "Merhaba",
        )

        self.assertNotIn(
            "format",
            calls[0],
        )

    def test_batch_applier_applies_composed_multi_patch_as_one_file_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            target = (
                root
                / "a.py"
            )

            target.write_bytes(
                b"A = 1\n"
                b"B = 2\n"
            )

            workspace = (
                SafeEditWorkspace(
                    root
                )
            )

            source = (
                workspace
                .read_edit_source(
                    "a.py"
                )
            )

            edits = (
                GroundedMultiPatchComposer()
                .compose(
                    patches=(
                        ProjectPatchSpec(
                            "a.py",
                            "A = 1",
                            "A = 10",
                        ),
                        ProjectPatchSpec(
                            "a.py",
                            "B = 2",
                            "B = 20",
                        ),
                    ),
                    source_by_path={
                        "a.py": source,
                    },
                )
            )

            from boru.tools import (
                ProjectEditProposal,
            )

            outcome = (
                BatchProjectEditApplier(
                    workspace=workspace
                )
                .apply_project_edit(
                    ProjectEditProposal(
                        instruction=(
                            "multi"
                        ),
                        edits=edits,
                    )
                )
            )

            self.assertEqual(
                len(
                    outcome.outcomes
                ),
                1,
            )

            self.assertEqual(
                target.read_text(
                    encoding="utf-8"
                ),
                (
                    "A = 10\n"
                    "B = 20\n"
                ),
            )

    def test_dependency_selector_adds_direct_local_import(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "config.py"
            ).write_bytes(
                b"RETRY = 3\n"
            )

            (
                root
                / "service.py"
            ).write_bytes(
                b"import config\n"
                b"\n"
                b"def run():\n"
                b"    return config.RETRY\n"
            )

            base = (
                FixedSelector(
                    (
                        "service.py",
                    )
                )
            )

            selector = (
                DependencyAwareProjectFileSelector(
                    base_selector=(
                        base
                    ),
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                    max_files=4,
                )
            )

            selection = (
                selector
                .select_files(
                    request=(
                        ProjectEditRequest(
                            "service.py içindeki sistemi "
                            "ilgili config ile uyumlu yap"
                        )
                    ),
                    available_paths=(
                        "config.py",
                        "service.py",
                    ),
                )
            )

            self.assertEqual(
                selection.paths,
                (
                    "service.py",
                    "config.py",
                ),
            )

    def test_dependency_selector_adds_reverse_importing_test(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "service.py"
            ).write_bytes(
                b"def run():\n"
                b"    return 1\n"
            )

            (
                root
                / "test_service.py"
            ).write_bytes(
                b"from service import run\n"
                b"\n"
                b"def test_run():\n"
                b"    assert run() == 1\n"
            )

            selector = (
                DependencyAwareProjectFileSelector(
                    base_selector=(
                        FixedSelector(
                            (
                                "service.py",
                            )
                        )
                    ),
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                    max_files=4,
                )
            )

            selection = (
                selector
                .select_files(
                    request=(
                        ProjectEditRequest(
                            "service.py davranışını değiştir "
                            "ve ilgili testi uyumlu yap"
                        )
                    ),
                    available_paths=(
                        "service.py",
                        "test_service.py",
                    ),
                )
            )

            self.assertEqual(
                selection.paths,
                (
                    "service.py",
                    "test_service.py",
                ),
            )

    def test_dependency_expansion_is_bounded(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "a.py"
            ).write_bytes(
                b"import b\n"
                b"import c\n"
                b"import d\n"
            )

            for name in (
                "b.py",
                "c.py",
                "d.py",
            ):
                (
                    root
                    / name
                ).write_bytes(
                    b"VALUE = 1\n"
                )

            selector = (
                DependencyAwareProjectFileSelector(
                    base_selector=(
                        FixedSelector(
                            (
                                "a.py",
                            )
                        )
                    ),
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                    max_files=2,
                )
            )

            selection = (
                selector
                .select_files(
                    request=(
                        ProjectEditRequest(
                            "a.py ve ilgili bağımlılıkları güncelle"
                        )
                    ),
                    available_paths=(
                        "a.py",
                        "b.py",
                        "c.py",
                        "d.py",
                    ),
                )
            )

            self.assertEqual(
                len(
                    selection.paths
                ),
                2,
            )

            self.assertEqual(
                selection.paths[0],
                "a.py",
            )

    def test_dependency_selector_does_not_expand_without_dependency_cue(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "a.py"
            ).write_bytes(
                b"import b\n"
            )

            (
                root
                / "b.py"
            ).write_bytes(
                b"X = 1\n"
            )

            selector = (
                DependencyAwareProjectFileSelector(
                    base_selector=(
                        FixedSelector(
                            (
                                "a.py",
                            )
                        )
                    ),
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    ),
                    max_files=4,
                )
            )

            selection = (
                selector
                .select_files(
                    request=(
                        ProjectEditRequest(
                            "a.py içindeki X değerini değiştir"
                        )
                    ),
                    available_paths=(
                        "a.py",
                        "b.py",
                    ),
                )
            )

            self.assertEqual(
                selection.paths,
                (
                    "a.py",
                ),
            )


if __name__ == "__main__":
    unittest.main()
