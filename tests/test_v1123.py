import tempfile
import unittest
from pathlib import Path

from boru.tools import (
    EditProposal,
    FallbackSmartEditProposalPreparer,
    RuleBasedAssignmentEditProposalPreparer,
    RuleBasedSmartEditRequestParser,
    SafeEditWorkspace,
    SmartEditNotApplicable,
)


class RecordingFallback:
    def __init__(
        self,
        proposal: EditProposal | None = None,
    ):
        self.calls = 0
        self._proposal = proposal

    def prepare_smart_edit(
        self,
        request,
    ) -> EditProposal:
        self.calls += 1

        if self._proposal is None:
            raise AssertionError(
                "Fallback çağrılmamalıydı."
            )

        return self._proposal


class DeterministicAssignmentSmartEditTests(
    unittest.TestCase
):
    def test_user_case_changes_quoted_assignment_without_llm(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "smart_edit_test.txt"

            target.write_bytes(
                b'model = "new"'
            )

            workspace = SafeEditWorkspace(
                root
            )

            fallback = RecordingFallback()

            preparer = (
                FallbackSmartEditProposalPreparer(
                    primary=(
                        RuleBasedAssignmentEditProposalPreparer(
                            workspace=workspace
                        )
                    ),
                    fallback=fallback,
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "smart_edit_test.txt'deki "
                    "model değerini final yap"
                )
            )

            proposal = preparer.prepare_smart_edit(
                request  # type: ignore[arg-type]
            )

            self.assertEqual(
                fallback.calls,
                0,
            )

            self.assertEqual(
                proposal.updated_content,
                'model = "final"',
            )

            self.assertIn(
                '-model = "new"\n'
                '+model = "final"',
                proposal.diff,
            )

            self.assertEqual(
                target.read_bytes(),
                b'model = "new"',
            )

    def test_existing_quote_style_is_preserved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "a.py").write_bytes(
                b"model = 'old'\n"
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.py'deki model "
                    "değerini final yap"
                )
            )

            proposal = (
                RuleBasedAssignmentEditProposalPreparer(
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    )
                )
                .prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )
            )

            self.assertEqual(
                proposal.updated_content,
                "model = 'final'\n",
            )

    def test_trailing_comment_is_preserved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "a.py").write_bytes(
                b'model = "old"  # active\r\n'
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.py'deki model "
                    "değerini new yap"
                )
            )

            proposal = (
                RuleBasedAssignmentEditProposalPreparer(
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    )
                )
                .prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )
            )

            self.assertEqual(
                proposal.updated_content,
                'model = "new"  # active\r\n',
            )

    def test_unquoted_numeric_assignment_stays_unquoted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "a.py").write_bytes(
                b"count = 3\n"
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.py'deki count "
                    "değerini 5 yap"
                )
            )

            proposal = (
                RuleBasedAssignmentEditProposalPreparer(
                    workspace=(
                        SafeEditWorkspace(
                            root
                        )
                    )
                )
                .prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )
            )

            self.assertEqual(
                proposal.updated_content,
                "count = 5\n",
            )

    def test_same_value_is_rejected_without_llm_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "a.py").write_bytes(
                b'model = "final"\n'
            )

            fallback = RecordingFallback()

            preparer = (
                FallbackSmartEditProposalPreparer(
                    primary=(
                        RuleBasedAssignmentEditProposalPreparer(
                            workspace=(
                                SafeEditWorkspace(
                                    root
                                )
                            )
                        )
                    ),
                    fallback=fallback,
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.py'deki model "
                    "değerini final yap"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "zaten mevcut",
            ):
                preparer.prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )

            self.assertEqual(
                fallback.calls,
                0,
            )

    def test_ambiguous_assignment_is_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "a.py").write_bytes(
                b'model = "one"\n'
                b'model = "two"\n'
            )

            fallback = RecordingFallback()

            preparer = (
                FallbackSmartEditProposalPreparer(
                    primary=(
                        RuleBasedAssignmentEditProposalPreparer(
                            workspace=(
                                SafeEditWorkspace(
                                    root
                                )
                            )
                        )
                    ),
                    fallback=fallback,
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    "a.py'deki model "
                    "değerini final yap"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "birden fazla",
            ):
                preparer.prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )

            self.assertEqual(
                fallback.calls,
                0,
            )

    def test_sensitive_file_is_blocked_before_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / ".env").write_bytes(
                b'SECRET = "old"\n'
            )

            fallback = RecordingFallback()

            preparer = (
                FallbackSmartEditProposalPreparer(
                    primary=(
                        RuleBasedAssignmentEditProposalPreparer(
                            workspace=(
                                SafeEditWorkspace(
                                    root
                                )
                            )
                        )
                    ),
                    fallback=fallback,
                )
            )

            request = (
                RuleBasedSmartEditRequestParser()
                .parse(
                    ".env'deki SECRET "
                    "değerini new yap"
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "Hassas",
            ):
                preparer.prepare_smart_edit(
                    request  # type: ignore[arg-type]
                )

            self.assertEqual(
                fallback.calls,
                0,
            )

    def test_non_assignment_instruction_falls_back(
        self,
    ) -> None:
        proposal = EditProposal(
            path="a.py",
            updated_content="x",
            expected_sha256="0" * 64,
            diff="diff",
            original_character_count=1,
            updated_character_count=1,
        )

        fallback = RecordingFallback(
            proposal
        )

        class AlwaysNotApplicable:
            def prepare_smart_edit(
                self,
                request,
            ) -> EditProposal:
                del request
                raise SmartEditNotApplicable(
                    "not applicable"
                )

        preparer = (
            FallbackSmartEditProposalPreparer(
                primary=(
                    AlwaysNotApplicable()
                ),
                fallback=fallback,
            )
        )

        result = preparer.prepare_smart_edit(
            object()  # type: ignore[arg-type]
        )

        self.assertIs(
            result,
            proposal,
        )

        self.assertEqual(
            fallback.calls,
            1,
        )


if __name__ == "__main__":
    unittest.main()