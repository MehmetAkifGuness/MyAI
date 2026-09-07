import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.code_index import SafeCodeIndex, SafeCodeRelationshipIndex
from boru.evaluation.models import Check, EvaluationReport, Verdict
from boru.improvement import (
    GoalDrivenChangeScopeResolver,
    ImprovementCoordinator,
    NaturalLanguageImprovementCoordinator,
)
from boru.release import build_release
from boru.tools import (
    LLMProjectEditProposalPreparer,
    SafeEditWorkspace,
    SafeProjectFileIndex,
    SafeWriteWorkspace,
)
from boru.tools.project_edit_models import ProjectEditRequest


class FakeWorkflow:
    def __init__(self):
        self.calls = []
        self.pending = False

    @property
    def has_pending(self):
        return self.pending

    def resolve(self, message):
        self.calls.append(message)
        if message.casefold().startswith("iyileştir:"):
            self.pending = True
            return "İYİLEŞTİRME ÖNERİSİ"
        return "İyileştirme onay bekliyor."


class FakeCoding:
    def __init__(self):
        self.messages = []

    @property
    def has_pending(self):
        return False

    def resolve(self, message):
        self.messages.append(message)
        return "CODING AGENT ÖNERİSİ"


class FakeApplier:
    allowed_paths = ()
    can_undo = False
    last_validation = None


class FakeEvaluator:
    def evaluate(self, paths):
        return EvaluationReport(
            paths=tuple(paths),
            fingerprints=(),
            checks=(Check("Test", Verdict.FAIL, "AssertionError: 1 != 2"),),
        )


class RepairingProjectModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.messages = []

    def generate_structured(self, messages, schema):
        self.messages.append(messages)
        return json.dumps(self.outputs.pop(0))


class GoalDrivenChangeScopeTests(unittest.TestCase):
    @staticmethod
    def _project(root):
        (root / "calculator.py").write_text(
            "def add(left, right):\n    return left - right\n",
            encoding="utf-8",
        )
        (root / "test_goal_calculator.py").write_text(
            "import unittest\n"
            "from calculator import add\n\n"
            "class GoalDrivenCalculatorTests(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n",
            encoding="utf-8",
        )

    def _resolver(self, root):
        return GoalDrivenChangeScopeResolver(
            root,
            SafeCodeIndex(root),
            SafeCodeRelationshipIndex(root),
        )

    def test_expands_unique_test_symbol_to_imported_implementation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)

            scope = self._resolver(root).resolve(
                "GoalDrivenCalculatorTests testindeki toplama hatasını bul ve düzelt"
            )

            self.assertEqual(
                scope.paths,
                ("calculator.py",),
            )
            self.assertIn("import ilişkisi", scope.evidence[-1])
            self.assertIn("test sözleşmesini değiştirmeden", scope.guidance)

    def test_explicit_file_scope_is_not_automatically_expanded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)

            scope = self._resolver(root).resolve(
                "test_goal_calculator.py dosyasındaki açıklamayı düzelt"
            )

            self.assertEqual(scope.paths, ("test_goal_calculator.py",))
            self.assertTrue(scope.explicit)

    def test_resolves_unique_file_stem_without_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)

            scope = self._resolver(root).resolve(
                "test_goal_calculator içindeki hatayı düzelt"
            )

            self.assertEqual(
                scope.paths,
                ("calculator.py",),
            )

    def test_natural_flow_passes_root_cause_guidance_and_safe_edit_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            workflow = FakeWorkflow()
            coordinator = NaturalLanguageImprovementCoordinator(
                workflow,
                self._resolver(root),
            )

            report = coordinator.resolve(
                "GoalDrivenCalculatorTests testindeki toplama hatasını bul ve düzelt"
            )

            self.assertIn("iyileştir: calculator.py |", workflow.calls[0])
            self.assertIn("test sözleşmesini değiştirmeden", workflow.calls[0])
            self.assertIn("import ilişkisi", report)

    def test_rejects_equally_ranked_implementation_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "second.py").write_text("VALUE = 2\n", encoding="utf-8")
            (root / "ambiguous_test.py").write_text(
                "import unittest\nimport first\nimport second\n\n"
                "class AmbiguousGoalTests(unittest.TestCase):\n"
                "    def test_values(self):\n        self.assertTrue(True)\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "eşit güçlü"):
                self._resolver(root).resolve(
                    "AmbiguousGoalTests testindeki hatayı bul ve düzelt"
                )


class ImprovementEvidenceContextTests(unittest.TestCase):
    def test_includes_bounded_baseline_failure_in_coding_task(self):
        coding = FakeCoding()
        coordinator = ImprovementCoordinator(
            coding,
            FakeApplier(),
            FakeEvaluator(),
            include_baseline_context=True,
            baseline_context_characters=200,
        )

        report = coordinator.resolve("iyileştir: calculator.py | toplama hatasını düzelt")

        self.assertIn("İYİLEŞTİRME ÖNERİSİ", report)
        self.assertIn("DOĞRULAMA_KANITI", coding.messages[0])
        self.assertIn("AssertionError: 1 != 2", coding.messages[0])

    def test_traceback_paths_do_not_expand_architect_scope(self):
        from boru.architecture import RuleBasedArchitectureRequestParser

        request = RuleBasedArchitectureRequestParser().parse_task(
            "Hatayı düzelt. Yalnızca şu dosyaları kapsa: calculator.py, test_goal_calculator.py"
            "\n\nDOĞRULAMA_KANITI:\nFile /workspace/unrelated.py failed"
        )

        self.assertEqual(
            request.file_scope,
            ("calculator.py", "test_goal_calculator.py"),
        )

    def test_internal_scope_marker_excludes_evidence_only_test_path(self):
        from boru.architecture import RuleBasedArchitectureRequestParser

        request = RuleBasedArchitectureRequestParser().parse_task(
            "Kök neden calculator.py; calculator_test.py test sözleşmesini koru."
            "\nBORU_DOSYA_KAPSAMI: calculator.py"
            "\n\nDOĞRULAMA_KANITI:\ncalculator_test.py başarısız"
        )

        self.assertEqual(request.file_scope, ("calculator.py",))

    def test_scoped_prepare_overrides_file_names_in_objective(self):
        from boru.architecture import RuleBasedArchitectureRequestParser

        coding = FakeCoding()
        coordinator = ImprovementCoordinator(
            coding,
            FakeApplier(),
            FakeEvaluator(),
            include_baseline_context=True,
        )

        coordinator.prepare_scoped(
            ("calculator.py",),
            "calculator_test.py sözleşmesini değiştirmeden yalnızca calculator.py dosyasını düzelt",
            validation_paths=("calculator_test.py",),
        )

        task = coding.messages[0].removeprefix("kodla: ")
        request = RuleBasedArchitectureRequestParser().parse_task(task)
        self.assertEqual(request.file_scope, ("calculator.py",))
        self.assertIn("BORU_DOSYA_KAPSAMI: calculator.py", task)


class ScopedProjectPlannerRepairTests(unittest.TestCase):
    def test_repairs_out_of_scope_creation_with_a_grounded_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "calculator.py").write_text(
                "def add(left, right):\n    return left - right\n",
                encoding="utf-8",
            )
            model = RepairingProjectModel(
                [
                    {
                        "patches": [],
                        "creates": [
                            {
                                "path": "calculator_test.py",
                                "content": "",
                                "reason": "test",
                            }
                        ],
                    },
                    {
                        "patches": [
                            {
                                "path": "calculator.py",
                                "old_text": "return left - right",
                                "new_text": "return left + right",
                                "reason": "toplama işlemini düzelt",
                            }
                        ],
                        "creates": [],
                    },
                ]
            )
            preparer = LLMProjectEditProposalPreparer(
                chat_model=model,
                file_index=SafeProjectFileIndex(root),
                file_selector=object(),
                workspace=SafeEditWorkspace(root),
                creation_validator=SafeWriteWorkspace(root),
                max_attempts=2,
            )

            proposal = preparer.prepare_project_edit(
                ProjectEditRequest(
                    "Toplama hatasını düzelt",
                    existing_file_scope=("calculator.py",),
                    new_file_scope=(),
                )
            )

            self.assertEqual(len(proposal.edits), 1)
            self.assertEqual(proposal.creations, ())
            self.assertEqual(len(model.messages), 2)
            self.assertIn("creates=[]", model.messages[1][1].content)


class ReleaseV140Tests(unittest.TestCase):
    def test_goal_driven_flow_requires_natural_and_relationship_features(self):
        with self.assertRaisesRegex(ValueError, "ilişki indeksi"):
            main_v170.build_application(goal_driven_change_enabled=True)

    def test_v140_release_enables_goal_driven_change_flow(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V1.4"), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V1.4")
            self.assertTrue(flags["natural_change_enabled"])
            self.assertTrue(flags["goal_driven_change_enabled"])
            self.assertFalse(flags["impact_analysis_enabled"])
            self.assertEqual(flags["project_edit_max_attempts"], 2)


if __name__ == "__main__":
    unittest.main()
