import os
import tempfile
import unittest
from pathlib import Path

from boru.tools import (
    ControlledWriteCoordinator,
    RiskBasedToolPolicy,
    RuleBasedWriteIntentDetector,
    RuleBasedWriteRequestParser,
    SafeWriteWorkspace,
    ToolCall,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
    WriteFileTool,
)


class ControlledWriteTests(
    unittest.TestCase
):
    def test_parser_accepts_header_format(
        self,
    ) -> None:
        request = (
            RuleBasedWriteRequestParser()
            .parse(
                "dosya oluştur: notes.txt\n"
                "İçerik:\n"
                "Merhaba Börü"
            )
        )

        self.assertIsNotNone(
            request
        )

        self.assertEqual(
            request.path,  # type: ignore[union-attr]
            "notes.txt",
        )

        self.assertEqual(
            request.content,  # type: ignore[union-attr]
            "Merhaba Börü",
        )

    def test_parser_accepts_write_format(
        self,
    ) -> None:
        request = (
            RuleBasedWriteRequestParser()
            .parse(
                "notes.txt dosyasına şunu yaz:\n"
                "abc"
            )
        )

        self.assertIsNotNone(
            request
        )

        self.assertEqual(
            request.path,  # type: ignore[union-attr]
            "notes.txt",
        )

        self.assertEqual(
            request.content,  # type: ignore[union-attr]
            "abc",
        )

    def test_intent_detector_recognizes_unsupported_edit(
        self,
    ) -> None:
        detector = (
            RuleBasedWriteIntentDetector()
        )

        self.assertTrue(
            detector.is_write_intent(
                "config.py dosyasını değiştir"
            )
        )

    def test_workspace_creates_new_utf8_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                SafeWriteWorkspace(
                    directory
                )
            )

            outcome = (
                workspace.write_text_file(
                    "hello.txt",
                    "Merhaba",
                )
            )

            self.assertEqual(
                (
                    Path(directory)
                    / "hello.txt"
                ).read_text(
                    encoding="utf-8"
                ),
                "Merhaba",
            )

            self.assertEqual(
                outcome.relative_path,
                "hello.txt",
            )

    def test_workspace_rejects_existing_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "hello.txt"
            )

            path.write_text(
                "old",
                encoding="utf-8",
            )

            workspace = (
                SafeWriteWorkspace(
                    directory
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "zaten mevcut",
            ):
                workspace.write_text_file(
                    "hello.txt",
                    "new",
                )

            self.assertEqual(
                path.read_text(
                    encoding="utf-8"
                ),
                "old",
            )

    def test_workspace_rejects_parent_traversal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                SafeWriteWorkspace(
                    directory
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "Workspace dışına",
            ):
                workspace.write_text_file(
                    "../escape.txt",
                    "x",
                )

    def test_workspace_rejects_windows_absolute_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                SafeWriteWorkspace(
                    directory
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "Mutlak",
            ):
                workspace.write_text_file(
                    r"C:\Windows\escape.txt",
                    "x",
                )

    def test_workspace_rejects_env_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                SafeWriteWorkspace(
                    directory
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "Hassas",
            ):
                workspace.write_text_file(
                    ".env",
                    "SECRET=x",
                )

    def test_workspace_rejects_git_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = (
                SafeWriteWorkspace(
                    directory
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "Hassas",
            ):
                workspace.write_text_file(
                    ".git/config",
                    "x",
                )

    def test_workspace_rejects_symlink_component_when_supported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            real = root / "real"
            real.mkdir()

            link = root / "link"

            try:
                os.symlink(
                    real,
                    link,
                    target_is_directory=True,
                )
            except OSError:
                self.skipTest(
                    "Bu ortamda symlink oluşturma izni yok."
                )

            workspace = (
                SafeWriteWorkspace(
                    root
                )
            )

            with self.assertRaisesRegex(
                ValueError,
                "Sembolik",
            ):
                workspace.write_text_file(
                    "link/file.txt",
                    "x",
                )

    def test_write_file_tool_has_write_risk(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = WriteFileTool(
                SafeWriteWorkspace(
                    directory
                )
            )

            self.assertEqual(
                tool.risk,
                ToolRisk.WRITE,
            )

    def test_write_tool_is_blocked_without_write_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = WriteFileTool(
                SafeWriteWorkspace(
                    directory
                )
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
                    tool_name="write_file",
                    arguments={
                        "path": "x.txt",
                        "content": "x",
                    },
                )
            )

            self.assertFalse(
                result.success
            )

            self.assertFalse(
                (
                    Path(directory)
                    / "x.txt"
                ).exists()
            )

    def test_stage_does_not_write_before_approval(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator = (
                self._build_coordinator(
                    Path(directory)
                )
            )

            response = (
                coordinator.resolve(
                    "dosya oluştur: notes.txt\n"
                    "İçerik:\n"
                    "Merhaba"
                )
            )

            self.assertIn(
                "henüz uygulanmadı",
                response or "",
            )

            self.assertFalse(
                (
                    Path(directory)
                    / "notes.txt"
                ).exists()
            )

    def test_explicit_approval_writes_file(
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
                "dosya oluştur: notes.txt\n"
                "İçerik:\n"
                "Merhaba"
            )

            response = (
                coordinator.resolve(
                    "onayla"
                )
            )

            self.assertEqual(
                response,
                "Dosya oluşturuldu: notes.txt",
            )

            self.assertEqual(
                (
                    root
                    / "notes.txt"
                ).read_text(
                    encoding="utf-8"
                ),
                "Merhaba",
            )

    def test_cancel_does_not_write_file(
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
                "dosya oluştur: notes.txt\n"
                "İçerik:\n"
                "Merhaba"
            )

            response = (
                coordinator.resolve(
                    "iptal"
                )
            )

            self.assertIn(
                "iptal edildi",
                response or "",
            )

            self.assertFalse(
                (
                    root
                    / "notes.txt"
                ).exists()
            )

    def test_second_write_is_blocked_while_approval_pending(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator = (
                self._build_coordinator(
                    Path(directory)
                )
            )

            coordinator.resolve(
                "dosya oluştur: one.txt\n"
                "İçerik:\n"
                "1"
            )

            response = coordinator.resolve(
                "dosya oluştur: two.txt\n"
                "İçerik:\n"
                "2"
            )

            self.assertIn(
                "Zaten onay bekleyen",
                response or "",
            )

    def test_unsupported_edit_returns_safe_guidance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator = (
                self._build_coordinator(
                    Path(directory)
                )
            )

            response = (
                coordinator.resolve(
                    "config.py dosyasını değiştir"
                )
            )

            self.assertIn(
                "yalnızca tam içerik verilen",
                response or "",
            )

    def test_sensitive_target_is_still_blocked_after_approval(
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
                "dosya oluştur: .env\n"
                "İçerik:\n"
                "SECRET=x"
            )

            response = (
                coordinator.resolve(
                    "onayla"
                )
            )

            self.assertIn(
                "Hassas",
                response or "",
            )

            self.assertFalse(
                (
                    root
                    / ".env"
                ).exists()
            )

    def test_memory_like_write_message_is_not_part_of_this_test_layer(
        self,
    ) -> None:
        detector = (
            RuleBasedWriteIntentDetector()
        )

        self.assertFalse(
            detector.is_write_intent(
                "Bunu hatırla: favori rengim mavi."
            )
        )

    @staticmethod
    def _build_coordinator(
        root: Path,
    ) -> ControlledWriteCoordinator:
        registry = ToolRegistry(
            [
                WriteFileTool(
                    SafeWriteWorkspace(
                        root
                    )
                )
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
        )


if __name__ == "__main__":
    unittest.main()