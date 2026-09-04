import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from boru.memory import ConservativeMemoryDecisionGate
from boru.tools import (
    ControlledWriteCoordinator,
    FilesystemOperation,
    FilesystemOperationError,
    RuleBasedFilesystemOperationParser,
    RuleBasedWriteIntentDetector,
    RuleBasedWriteRequestParser,
    SafeFilesystemOperationWorkspace,
)


class UnexpectedExecutor:
    def execute(self, call):
        del call
        raise AssertionError("Filesystem akışı write executor kullanmamalı.")


def build_coordinator(root: Path) -> ControlledWriteCoordinator:
    return ControlledWriteCoordinator(
        parser=RuleBasedWriteRequestParser(),
        intent_detector=RuleBasedWriteIntentDetector(),
        executor=UnexpectedExecutor(),
        filesystem_parser=RuleBasedFilesystemOperationParser(),
        filesystem_workspace=SafeFilesystemOperationWorkspace(root),
    )


class FilesystemOperationParserTests(unittest.TestCase):
    def test_memory_gate_rejects_filesystem_commands(self) -> None:
        gate = ConservativeMemoryDecisionGate()

        for message in (
            "a.txt dosyasını sil",
            "a.txt dosyasını archive/a.txt konumuna taşı",
            "reports klasörünü oluştur",
        ):
            with self.subTest(message=message):
                self.assertFalse(gate.should_evaluate(message))

    def test_parses_all_explicit_operation_formats(self) -> None:
        parser = RuleBasedFilesystemOperationParser()
        cases = (
            ("dosya sil: notes/a.txt", FilesystemOperation.DELETE_FILE),
            ("dosya taşı: a.txt -> archive/a.txt", FilesystemOperation.MOVE_FILE),
            ("dosya yeniden adlandır: a.txt -> b.txt", FilesystemOperation.RENAME_FILE),
            ("klasör oluştur: reports", FilesystemOperation.MAKE_DIRECTORY),
        )

        for message, operation in cases:
            with self.subTest(message=message):
                request = parser.parse(message)
                self.assertIsNotNone(request)
                self.assertIs(request.operation, operation)

    def test_detects_malformed_operation_intent(self) -> None:
        parser = RuleBasedFilesystemOperationParser()
        self.assertIsNone(parser.parse("bu dosyayı sil"))
        self.assertTrue(parser.is_operation_intent("bu dosyayı sil"))


class SafeFilesystemOperationWorkspaceTests(unittest.TestCase):
    def test_delete_rejects_stale_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.txt"
            target.write_text("first", encoding="utf-8")
            workspace = SafeFilesystemOperationWorkspace(root)
            proposal = workspace.prepare(
                RuleBasedFilesystemOperationParser().parse("dosya sil: a.txt")
            )
            target.write_text("external", encoding="utf-8")

            with self.assertRaisesRegex(FilesystemOperationError, "değişmiş"):
                workspace.apply(proposal)

            self.assertEqual(target.read_text(encoding="utf-8"), "external")

    def test_move_never_overwrites_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("source", encoding="utf-8")
            (root / "b.txt").write_text("target", encoding="utf-8")
            workspace = SafeFilesystemOperationWorkspace(root)
            request = RuleBasedFilesystemOperationParser().parse(
                "dosya taşı: a.txt -> b.txt"
            )

            with self.assertRaisesRegex(FilesystemOperationError, "zaten mevcut"):
                workspace.prepare(request)

            self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "source")
            self.assertEqual((root / "b.txt").read_text(encoding="utf-8"), "target")

    def test_failed_move_removes_new_link_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "a.txt"
            source.write_text("source", encoding="utf-8")
            workspace = SafeFilesystemOperationWorkspace(root)
            proposal = workspace.prepare(
                RuleBasedFilesystemOperationParser().parse(
                    "dosya taşı: a.txt -> b.txt"
                )
            )
            original_unlink = Path.unlink

            def fail_source_unlink(path, *args, **kwargs):
                if path == source:
                    raise OSError("simulated unlink failure")
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", new=fail_source_unlink):
                with self.assertRaisesRegex(FilesystemOperationError, "geri alındı"):
                    workspace.apply(proposal)

            self.assertTrue(source.exists())
            self.assertFalse((root / "b.txt").exists())

    def test_sensitive_and_traversal_paths_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = SafeFilesystemOperationWorkspace(root)
            parser = RuleBasedFilesystemOperationParser()

            for message in (
                "klasör oluştur: ../outside",
                "klasör oluştur: .git/new",
                "dosya sil: .env",
            ):
                with self.subTest(message=message):
                    with self.assertRaises(FilesystemOperationError):
                        workspace.prepare(parser.parse(message))

    def test_directory_cannot_be_deleted_as_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "folder").mkdir()

            with self.assertRaisesRegex(FilesystemOperationError, "normal bir dosya"):
                SafeFilesystemOperationWorkspace(root).prepare(
                    RuleBasedFilesystemOperationParser().parse("dosya sil: folder")
                )


class ControlledFilesystemOperationTests(unittest.TestCase):
    def test_delete_requires_specific_high_risk_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.txt"
            target.write_text("delete me", encoding="utf-8")
            coordinator = build_coordinator(root)

            preview = coordinator.resolve("dosya sil: a.txt")
            self.assertIn("Risk: DESTRUCTIVE", preview or "")
            self.assertTrue(target.exists())

            generic = coordinator.resolve("onayla")
            self.assertIn("silmeyi onayla", generic or "")
            self.assertTrue(target.exists())

            result = coordinator.resolve("silmeyi onayla")
            self.assertIn("Dosya silindi", result or "")
            self.assertFalse(target.exists())

    def test_cancelled_delete_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.txt"
            target.write_text("keep", encoding="utf-8")
            coordinator = build_coordinator(root)

            coordinator.resolve("dosya sil: a.txt")
            response = coordinator.resolve("iptal")

            self.assertIn("iptal edildi", response or "")
            self.assertTrue(target.exists())

    def test_move_and_rename_are_previewed_then_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "a.txt").write_text("value", encoding="utf-8")
            coordinator = build_coordinator(root)

            preview = coordinator.resolve("dosya taşı: a.txt -> archive/a.txt")
            self.assertIn("İşlem: MOVE", preview or "")
            coordinator.resolve("onayla")
            self.assertFalse((root / "a.txt").exists())
            self.assertTrue((root / "archive" / "a.txt").exists())

            preview = coordinator.resolve(
                "dosya yeniden adlandır: archive/a.txt -> archive/b.txt"
            )
            self.assertIn("İşlem: RENAME", preview or "")
            coordinator.resolve("onayla")
            self.assertFalse((root / "archive" / "a.txt").exists())
            self.assertEqual(
                (root / "archive" / "b.txt").read_text(encoding="utf-8"),
                "value",
            )

    def test_mkdir_is_previewed_then_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = build_coordinator(root)

            preview = coordinator.resolve("klasör oluştur: reports")
            self.assertIn("İşlem: MKDIR", preview or "")
            self.assertFalse((root / "reports").exists())
            result = coordinator.resolve("onayla")

            self.assertIn("Klasör oluşturuldu", result or "")
            self.assertTrue((root / "reports").is_dir())

    def test_malformed_operation_returns_safe_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            response = build_coordinator(Path(directory)).resolve("bu dosyayı sil")
            self.assertIn("dosya sil: path", response or "")

    def test_pending_operation_blocks_other_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("value", encoding="utf-8")
            coordinator = build_coordinator(root)
            coordinator.resolve("dosya sil: a.txt")

            response = coordinator.resolve("klasör oluştur: reports")

            self.assertIn("Zaten onay bekleyen", response or "")
            self.assertFalse((root / "reports").exists())


if __name__ == "__main__":
    unittest.main()
