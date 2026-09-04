import tempfile
import unittest
from pathlib import Path

from boru.tools import (
    RuleBasedEditRequestParser,
    SafeEditWorkspace,
    UnifiedDiffRenderer,
)


class DiffOutputHygieneTests(
    unittest.TestCase
):
    def test_no_terminal_newline_does_not_glue_removed_and_added_lines(
        self,
    ) -> None:
        diff = UnifiedDiffRenderer().render(
            original='model = "old"',
            updated='model = "new"',
            fromfile="a.txt (mevcut)",
            tofile="a.txt (önerilen)",
        )

        self.assertIn(
            '-model = "old"\n+model = "new"',
            diff,
        )

        self.assertNotIn(
            '-model = "old"+model = "new"',
            diff,
        )

    def test_no_terminal_newline_is_marked_for_both_versions(
        self,
    ) -> None:
        diff = UnifiedDiffRenderer().render(
            original="old",
            updated="new",
            fromfile="a.txt (mevcut)",
            tofile="a.txt (önerilen)",
        )

        self.assertIn(
            "\\ No newline at end of current file",
            diff,
        )

        self.assertIn(
            "\\ No newline at end of proposed file",
            diff,
        )

    def test_terminal_newline_files_do_not_receive_no_newline_marker(
        self,
    ) -> None:
        diff = UnifiedDiffRenderer().render(
            original="old\n",
            updated="new\n",
            fromfile="a.txt (mevcut)",
            tofile="a.txt (önerilen)",
        )

        self.assertNotIn(
            "No newline at end",
            diff,
        )

        self.assertIn(
            "-old\n+new",
            diff,
        )

    def test_safe_edit_workspace_uses_hygienic_diff_renderer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.txt"

            target.write_bytes(
                b' model = "old"'.lstrip()
            )

            request = (
                RuleBasedEditRequestParser()
                .parse(
                    "dosya düzenle: a.txt\n"
                    "Eski:\n"
                    'model = "old"\n'
                    "Yeni:\n"
                    'model = "new"'
                )
            )

            self.assertIsNotNone(
                request
            )

            proposal = (
                SafeEditWorkspace(root)
                .prepare_exact_replacement(
                    request  # type: ignore[arg-type]
                )
            )

            self.assertIn(
                '-model = "old"\n+model = "new"',
                proposal.diff,
            )

            self.assertEqual(
                target.read_bytes(),
                b'model = "old"',
            )

    def test_diff_rendering_does_not_change_crlf_edit_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.txt"

            target.write_bytes(
                b"old\r\n"
            )

            request = (
                RuleBasedEditRequestParser()
                .parse(
                    "dosya düzenle: a.txt\n"
                    "Eski:\n"
                    "old\n"
                    "Yeni:\n"
                    "new"
                )
            )

            self.assertIsNotNone(
                request
            )

            proposal = (
                SafeEditWorkspace(root)
                .prepare_exact_replacement(
                    request  # type: ignore[arg-type]
                )
            )

            self.assertEqual(
                proposal.updated_content,
                "new\r\n",
            )

            self.assertNotIn(
                "No newline at end",
                proposal.diff,
            )


if __name__ == "__main__":
    unittest.main()