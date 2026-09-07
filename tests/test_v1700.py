import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.code_index import SafeCodeImpactIndex, SafeCodeIndex, SafeCodeRelationshipIndex
from boru.improvement import (
    GoalDrivenChangeScopeResolver,
    NaturalLanguageImprovementCoordinator,
)
from boru.release import build_release


class ScopedImprovementWorkflow:
    def __init__(self):
        self.pending = False
        self.prepared = []
        self.messages = []

    @property
    def has_pending(self):
        return self.pending

    def prepare_scoped(self, paths, objective, *, validation_paths=()):
        self.prepared.append((tuple(paths), objective, tuple(validation_paths)))
        self.pending = True
        return "İYİLEŞTİRME ÖNERİSİ\nUygulamak için 'iyileştirmeyi onayla'."

    def resolve(self, message):
        self.messages.append(message)
        normalized = " ".join(message.casefold().split())
        if self.pending and normalized == "iyileştirmeyi onayla":
            self.pending = False
            return "Coding Agent değişikliği uygulandı: 1 dosya"
        if self.pending and normalized in {"iptal", "vazgeç"}:
            self.pending = False
            return "İyileştirme iptal edildi."
        if self.pending:
            return "İyileştirme onay bekliyor."
        return None


class RuntimeRepairFlowTests(unittest.TestCase):
    @staticmethod
    def _project(root):
        (root / "runtime_math.py").write_text(
            "def add(left, right):\n    return left - right\n",
            encoding="utf-8",
        )
        (root / "runtime_math_test.py").write_text(
            "import unittest\nfrom runtime_math import add\n\n"
            "class RuntimeMathTests(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n",
            encoding="utf-8",
        )

    def _coordinator(self, root, workflow):
        scope = GoalDrivenChangeScopeResolver(
            root,
            SafeCodeIndex(root),
            SafeCodeRelationshipIndex(root),
            SafeCodeImpactIndex(root),
        )
        return NaturalLanguageImprovementCoordinator(
            workflow,
            scope,
            runtime_repair_enabled=True,
        )

    def test_routes_explicit_test_to_implementation_and_validation_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            workflow = ScopedImprovementWorkflow()
            coordinator = self._coordinator(root, workflow)

            report = coordinator.resolve(
                "ajan: runtime_math_test.py testini sandbox içinde çalıştır ve hatayı düzelt"
            )

            self.assertIn("ÇALIŞMA ZAMANI ONARIM AKIŞI", report)
            paths, objective, validation_paths = workflow.prepared[0]
            self.assertEqual(paths, ("runtime_math.py",))
            self.assertEqual(validation_paths, ("runtime_math_test.py",))
            self.assertNotIn("ajan:", objective.casefold())
            self.assertIn("test sözleşmesini değiştirmeden", objective)
            self.assertIn("Doğrulama kapsamı: runtime_math_test.py", report)

            self.assertIn("onay bekliyor", coordinator.resolve("onayla").casefold())
            self.assertIn(
                "değişikliği uygulandı",
                coordinator.resolve("iyileştirmeyi onayla"),
            )

    def test_non_mutating_agent_test_request_is_not_captured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            coordinator = self._coordinator(root, ScopedImprovementWorkflow())

            self.assertIsNone(
                coordinator.resolve(
                    "ajan: runtime_math_test.py testini sandbox içinde çalıştır ve sonucu açıkla"
                )
            )


class ReleaseV170Tests(unittest.TestCase):
    def test_runtime_repair_requires_test_and_goal_features(self):
        with self.assertRaisesRegex(ValueError, "hedefli test ajanı"):
            main_v170.build_application(runtime_repair_enabled=True)

    def test_default_release_enables_runtime_repair(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release(), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V1.7")
            self.assertTrue(flags["runtime_test_agent_enabled"])
            self.assertTrue(flags["runtime_repair_enabled"])


if __name__ == "__main__":
    unittest.main()
