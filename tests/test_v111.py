import os
import tempfile
import unittest
from pathlib import Path

from boru.tools import (
    ControlledWriteCoordinator,
    EditFileTool,
    RiskBasedToolPolicy,
    RuleBasedEditRequestParser,
    RuleBasedWriteIntentDetector,
    RuleBasedWriteRequestParser,
    SafeEditWorkspace,
    SafeWriteWorkspace,
    ToolCall,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
    WriteFileTool,
)


class ControlledExistingFileEditTests(
    unittest.TestCase
):
    def test_edit_parser_accepts_header_format(
        self,
    ) -> None:
        request = (
            RuleBasedEditRequestParser()
            .parse(
                "dosya düzenle: boru/config.py\n"
                "Eski:\n"
                'model_name: str = "llama3.1"\n'
                "Yeni:\n"
                'model_name: str = "llama3.2"'
            )
        )

        self.assertIsNotNone(
            request
        )
        self.assertEqual(
            request.path,  # type: ignore[union-attr]
            "boru/config.py",
        )
        self.assertEqual(
            request.old_text,  # type: ignore[union-attr]
            'model_name: str = "llama3.1"',
        )
        self.assertEqual(
            request.new_text,  # type: ignore[union-attr]
            'model_name: str = "llama3.2"',
        )

    def test_edit_parser_accepts_natural_file_format(
        self,
    ) -> None:
        request = (
            RuleBasedEditRequestParser()
            .parse(
                "boru/config.py dosyasında şunu değiştir:\n"
                "Eski:\n"
                "abc\n"
                "Yeni:\n"
                "xyz"
            )
        )

        self.assertIsNotNone(
            request
        )
        self.assertEqual(
            request.path,  # type: ignore[union-attr]
            "boru/config.py",
        )

    def test_workspace_prepares_unique_exact_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.py"
            path.write_text(
                'model = "old"\nvalue = 1\n',
                encoding="utf-8",
            )

            request = self._parse_edit(
                "config.py",
                'model = "old"',
                'model = "new"',
            )

            proposal = (
                SafeEditWorkspace(root)
                .prepare_exact_replacement(
                    request
                )
            )

            self.assertIn(
                '-model = "old"',
                proposal.diff,
            )
            self.assertIn(
                '+model = "new"',
                proposal.diff,
            )
            self.assertIn(
                'model = "new"',
                proposal.updated_content,
            )
            self.assertEqual(
                path.read_text(
                    encoding="utf-8"
                ),
                'model = "old"\nvalue = 1\n',
            )

    def test_workspace_rejects_missing_old_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text(
                "hello",
                encoding="utf-8",
            )

            request = self._parse_edit(
                "a.txt",
                "missing",
                "new",
            )

            with self.assertRaisesRegex(
                ValueError,
                "bulunamadı",
            ):
                SafeEditWorkspace(
                    root
                ).prepare_exact_replacement(
                    request
                )

    def test_workspace_rejects_ambiguous_old_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text(
                "same\nsame\n",
                encoding="utf-8",
            )

            request = self._parse_edit(
                "a.txt",
                "same",
                "changed",
            )

            with self.assertRaisesRegex(
                ValueError,
                "birden fazla",
            ):
                SafeEditWorkspace(
                    root
                ).prepare_exact_replacement(
                    request
                )

    def test_workspace_rejects_sensitive_env_edit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "SECRET=x",
                encoding="utf-8",
            )

            request = self._parse_edit(
                ".env",
                "SECRET=x",
                "SECRET=y",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Hassas",
            ):
                SafeEditWorkspace(
                    root
                ).prepare_exact_replacement(
                    request
                )

    def test_workspace_rejects_parent_traversal_edit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            request = self._parse_edit(
                "../a.txt",
                "x",
                "y",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Workspace dışına",
            ):
                SafeEditWorkspace(
                    root
                ).prepare_exact_replacement(
                    request
                )

    def test_workspace_rejects_windows_absolute_edit_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = self._parse_edit(
                r"C:\Windows\a.txt",
                "x",
                "y",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Mutlak",
            ):
                SafeEditWorkspace(
                    directory
                ).prepare_exact_replacement(
                    request
                )

    def test_workspace_rejects_symlink_edit_when_supported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real.txt"
            real.write_text(
                "old",
                encoding="utf-8",
            )
            link = root / "link.txt"

            try:
                os.symlink(
                    real,
                    link,
                )
            except OSError:
                self.skipTest(
                    "Bu ortamda symlink oluşturma izni yok."
                )

            request = self._parse_edit(
                "link.txt",
                "old",
                "new",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Sembolik",
            ):
                SafeEditWorkspace(
                    root
                ).prepare_exact_replacement(
                    request
                )

    def test_edit_file_tool_has_write_risk(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = EditFileTool(
                SafeEditWorkspace(
                    directory
                )
            )

            self.assertEqual(
                tool.risk,
                ToolRisk.WRITE,
            )

    def test_edit_tool_is_blocked_without_write_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.txt"
            path.write_text(
                "old",
                encoding="utf-8",
            )
            workspace = SafeEditWorkspace(
                root
            )
            proposal = (
                workspace
                .prepare_exact_replacement(
                    self._parse_edit(
                        "a.txt",
                        "old",
                        "new",
                    )
                )
            )
            tool = EditFileTool(
                workspace
            )
            executor = ToolExecutor(
                registry=ToolRegistry(
                    [tool]
                ),
                policy=RiskBasedToolPolicy(
                    allowed_risks=(
                        ToolRisk.READ_ONLY,
                    )
                ),
            )

            result = executor.execute(
                ToolCall(
                    tool_name="edit_file",
                    arguments={
                        "path": proposal.path,
                        "content": (
                            proposal.updated_content
                        ),
                        "expected_sha256": (
                            proposal.expected_sha256
                        ),
                    },
                )
            )

            self.assertFalse(
                result.success
            )
            self.assertEqual(
                path.read_text(
                    encoding="utf-8"
                ),
                "old",
            )

    def test_stage_edit_does_not_change_file_before_approval(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.txt"
            path.write_text(
                "old value\n",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            response = coordinator.resolve(
                self._edit_message(
                    "a.txt",
                    "old value",
                    "new value",
                )
            )

            self.assertIn(
                "Düzenleme hazırlandı",
                response or "",
            )
            self.assertIn(
                "Diff:",
                response or "",
            )
            self.assertEqual(
                path.read_text(
                    encoding="utf-8"
                ),
                "old value\n",
            )

    def test_explicit_approval_applies_edit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.txt"
            path.write_text(
                "old value\n",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            coordinator.resolve(
                self._edit_message(
                    "a.txt",
                    "old value",
                    "new value",
                )
            )

            response = coordinator.resolve(
                "onayla"
            )

            self.assertEqual(
                response,
                "Dosya güncellendi: a.txt",
            )
            self.assertEqual(
                path.read_text(
                    encoding="utf-8"
                ),
                "new value\n",
            )

    def test_cancelled_edit_does_not_change_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.txt"
            path.write_text(
                "old",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            coordinator.resolve(
                self._edit_message(
                    "a.txt",
                    "old",
                    "new",
                )
            )

            response = coordinator.resolve(
                "iptal"
            )

            self.assertIn(
                "iptal edildi",
                response or "",
            )
            self.assertEqual(
                path.read_text(
                    encoding="utf-8"
                ),
                "old",
            )

    def test_edit_is_rejected_if_file_changes_after_preview(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.txt"
            path.write_text(
                "old",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            coordinator.resolve(
                self._edit_message(
                    "a.txt",
                    "old",
                    "new",
                )
            )

            path.write_text(
                "changed externally",
                encoding="utf-8",
            )

            response = coordinator.resolve(
                "onayla"
            )

            self.assertIn(
                "önizlemeden sonra değişmiş",
                response or "",
            )
            self.assertEqual(
                path.read_text(
                    encoding="utf-8"
                ),
                "changed externally",
            )

    def test_edit_preserves_utf8_bom(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "bom.txt"
            path.write_bytes(
                b"\xef\xbb\xbfold"
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            coordinator.resolve(
                self._edit_message(
                    "bom.txt",
                    "old",
                    "new",
                )
            )
            coordinator.resolve(
                "onayla"
            )

            self.assertEqual(
                path.read_bytes(),
                b"\xef\xbb\xbfnew",
            )

    def test_atomic_edit_leaves_no_temp_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.txt"
            path.write_text(
                "old",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            coordinator.resolve(
                self._edit_message(
                    "a.txt",
                    "old",
                    "new",
                )
            )
            coordinator.resolve(
                "onayla"
            )

            temp_files = list(
                root.glob(
                    ".a.txt.*.tmp"
                )
            )
            self.assertEqual(
                temp_files,
                [],
            )

    def test_extended_coordinator_still_creates_new_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            coordinator.resolve(
                "dosya oluştur: new.txt\n"
                "İçerik:\n"
                "hello"
            )
            response = coordinator.resolve(
                "onayla"
            )

            self.assertEqual(
                response,
                "Dosya oluşturuldu: new.txt",
            )
            self.assertEqual(
                (root / "new.txt").read_text(
                    encoding="utf-8"
                ),
                "hello",
            )

    def test_second_change_is_blocked_while_edit_pending(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text(
                "old",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            coordinator.resolve(
                self._edit_message(
                    "a.txt",
                    "old",
                    "new",
                )
            )

            response = coordinator.resolve(
                "dosya oluştur: b.txt\n"
                "İçerik:\n"
                "b"
            )

            self.assertIn(
                "Zaten onay bekleyen",
                response or "",
            )
            self.assertFalse(
                (root / "b.txt").exists()
            )

    def test_incomplete_edit_request_returns_exact_replace_guidance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.py").write_text(
                "x=1",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            response = coordinator.resolve(
                "config.py dosyasını değiştir"
            )

            self.assertIn(
                "exact-replace",
                response or "",
            )
            self.assertIn(
                "Eski:",
                response or "",
            )
            self.assertIn(
                "Yeni:",
                response or "",
            )

    def test_invalid_same_old_and_new_is_reported_safely(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text(
                "same",
                encoding="utf-8",
            )
            coordinator = (
                self._build_coordinator(
                    root
                )
            )

            response = coordinator.resolve(
                self._edit_message(
                    "a.txt",
                    "same",
                    "same",
                )
            )

            self.assertIn(
                "Düzenleme isteği geçersiz",
                response or "",
            )

    def test_binary_file_edit_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "binary.dat").write_bytes(
                b"abc\x00def"
            )

            request = self._parse_edit(
                "binary.dat",
                "abc",
                "xyz",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Binary",
            ):
                SafeEditWorkspace(
                    root
                ).prepare_exact_replacement(
                    request
                )

    @staticmethod
    def _edit_message(
        path: str,
        old_text: str,
        new_text: str,
    ) -> str:
        return (
            f"dosya düzenle: {path}\n"
            "Eski:\n"
            f"{old_text}\n"
            "Yeni:\n"
            f"{new_text}"
        )

    @staticmethod
    def _parse_edit(
        path: str,
        old_text: str,
        new_text: str,
    ):
        request = (
            RuleBasedEditRequestParser()
            .parse(
                ControlledExistingFileEditTests
                ._edit_message(
                    path,
                    old_text,
                    new_text,
                )
            )
        )

        if request is None:
            raise AssertionError(
                "Test edit request parse edilemedi."
            )

        return request

    @staticmethod
    def _build_coordinator(
        root: Path,
    ) -> ControlledWriteCoordinator:
        write_workspace = (
            SafeWriteWorkspace(
                root
            )
        )
        edit_workspace = (
            SafeEditWorkspace(
                root
            )
        )

        registry = ToolRegistry(
            [
                WriteFileTool(
                    write_workspace
                ),
                EditFileTool(
                    edit_workspace
                ),
            ]
        )

        executor = ToolExecutor(
            registry=registry,
            policy=RiskBasedToolPolicy(
                allowed_risks=(
                    ToolRisk.WRITE,
                )
            ),
        )

        return ControlledWriteCoordinator(
            parser=(
                RuleBasedWriteRequestParser()
            ),
            intent_detector=(
                RuleBasedWriteIntentDetector()
            ),
            executor=executor,
            edit_parser=(
                RuleBasedEditRequestParser()
            ),
            edit_preparer=(
                edit_workspace
            ),
        )


if __name__ == "__main__":
    unittest.main()