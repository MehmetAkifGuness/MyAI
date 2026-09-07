import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from boru.evaluation import EvidenceEvaluator
from boru.improvement import VerifiedImprovementApplier, ImprovementCoordinator
from boru.tools.command_executor import BoundedCommandExecutor
from boru.tools.edit_models import EditProposal
from boru.tools.edit_workspace import SafeEditWorkspace
from boru.tools.project_edit_models import ProjectEditProposal


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests/__init__.py").write_text("", encoding="utf-8")
        (self.root / "tests/test_a.py").write_text(
            "import unittest\nimport a\nclass Values(unittest.TestCase):\n"
            "    def test_value(self):\n        self.assertEqual(a.VALUE, 2)\n", encoding="utf-8")
        # Test-only runner for the trusted synthetic fixtures above. Product uses Docker exclusively.
        self.applier = VerifiedImprovementApplier(
            self.root, lambda root: EvidenceEvaluator(root, BoundedCommandExecutor(root)))
        self.applier.allowed_paths = ("a.py",)

    def tearDown(self):
        self.temp.cleanup()

    def proposal(self, value):
        source = SafeEditWorkspace(self.root).read_edit_source("a.py")
        content = f"VALUE = {value}\n"
        return ProjectEditProposal("VALUE güncelle", (
            EditProposal("a.py", content, source.sha256, f"VALUE -> {value}", len(source.content), len(content)),))

    def test_validated_edit_and_guarded_rollback(self):
        self.applier.apply_project_edit(self.proposal(2))
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 2\n")
        self.applier.rollback()
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 1\n")

    def test_failed_candidate_does_not_modify_source(self):
        with self.assertRaisesRegex(ValueError, "Geçici kopya"):
            self.applier.apply_project_edit(self.proposal(3))
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 1\n")

    def test_stale_preview_is_rejected(self):
        proposal = self.proposal(2)
        (self.root / "a.py").write_text("VALUE = 5\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "kaynak değişmiş"):
            self.applier.apply_project_edit(proposal)
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 5\n")

    def test_rollback_preserves_external_edits(self):
        self.applier.apply_project_edit(self.proposal(2))
        (self.root / "a.py").write_text("VALUE = 9\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.applier.rollback()
        self.assertEqual((self.root / "a.py").read_text(), "VALUE = 9\n")

    def test_outside_scope_cannot_be_applied(self):
        self.applier.allowed_paths = ("b.py",)
        with self.assertRaisesRegex(ValueError, "kapsam dışında"):
            self.applier.apply_project_edit(self.proposal(2))

    def test_only_improvement_confirmation_reaches_coding(self):
        coding = Mock()
        coding.has_pending = True
        coding.resolve.return_value = "Applied"
        coordinator = ImprovementCoordinator(coding, self.applier, Mock())
        for message in ("onayla", "kod değişikliğini onayla"):
            self.assertIn("onay bekliyor", coordinator.resolve(message))
        coding.resolve.assert_not_called()
        coordinator.resolve("iyileştirmeyi onayla")
        coding.resolve.assert_called_once_with("kod değişikliğini onayla")


if __name__ == "__main__":
    unittest.main()
