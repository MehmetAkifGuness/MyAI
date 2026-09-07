import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.agent import ReadOnlyToolAgent
from boru.code_index import CodeSearchTool
from boru.code_index import SafeCodeImpactIndex, SafeCodeIndex, SafeCodeRelationshipIndex
from boru.evaluation import EvidenceEvaluator
from boru.improvement import GoalDrivenChangeScopeResolver, NaturalLanguageImprovementCoordinator
from boru.release import build_release
from boru.sandbox import TargetedSandboxTestTool
from boru.tools import ReadFileTool, ReadOnlyWorkspace, RiskBasedToolPolicy, ToolExecutor, ToolRegistry, ToolRisk
from boru.tools.command_models import CommandExecutionResult


class ScopedWorkflow:
    def __init__(self):
        self.pending = False
        self.prepared = []

    @property
    def has_pending(self):
        return self.pending

    def prepare_scoped(self, paths, objective, *, validation_paths=()):
        self.prepared.append((tuple(paths), objective, tuple(validation_paths)))
        self.pending = True
        return "İYİLEŞTİRME ÖNERİSİ\nUygulamak için 'iyileştirmeyi onayla'."

    def resolve(self, message):
        if self.pending and " ".join(message.casefold().split()) == "iyileştirmeyi onayla":
            self.pending = False
            return "Coding Agent değişikliği uygulandı: 2 dosya"
        return "İyileştirme onay bekliyor."


class UnusedExecutor:
    def execute(self, spec):
        raise AssertionError(f"Beklenmeyen test çalıştırma: {spec}")


class PassingSandboxExecutor:
    def __init__(self):
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        return CommandExecutionResult(
            command=command,
            exit_code=0,
            duration_seconds=0.1,
            output=".\nRan 1 test in 0.001s\n\nOK\n",
        )


class UnusedModel:
    def generate(self, messages):
        raise AssertionError("Çoklu test raporu model kullanmamalıdır.")

    def generate_structured(self, messages, schema):
        raise AssertionError("Çoklu test raporu model kullanmamalıdır.")


class BatchRuntimeRepairTests(unittest.TestCase):
    @staticmethod
    def _project(root):
        (root / "pricing.py").write_text("TAX_RATE = 0.10\n", encoding="utf-8")
        (root / "stock.py").write_text("MIN_STOCK = 0\n", encoding="utf-8")
        (root / "pricing_test.py").write_text(
            "import unittest\nfrom pricing import TAX_RATE\n\n"
            "class PricingTests(unittest.TestCase):\n"
            "    def test_tax(self):\n        self.assertEqual(TAX_RATE, 0.20)\n",
            encoding="utf-8",
        )
        (root / "stock_test.py").write_text(
            "import unittest\nfrom stock import MIN_STOCK\n\n"
            "class StockTests(unittest.TestCase):\n"
            "    def test_minimum(self):\n        self.assertEqual(MIN_STOCK, 1)\n",
            encoding="utf-8",
        )

    @staticmethod
    def _resolver(root, *, batch=True):
        return GoalDrivenChangeScopeResolver(
            root,
            SafeCodeIndex(root),
            SafeCodeRelationshipIndex(root),
            SafeCodeImpactIndex(root),
            batch_runtime_repair_enabled=batch,
        )

    def test_groups_multiple_tests_by_unique_implementation_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)

            scope = self._resolver(root).resolve_runtime_repair(
                "pricing_test.py ve stock_test.py testlerini sandbox içinde çalıştır, "
                "hataları kök nedene göre grupla ve düzelt"
            )

            self.assertEqual(scope.paths, ("pricing.py", "stock.py"))
            self.assertEqual(
                scope.validation_paths,
                ("pricing_test.py", "stock_test.py"),
            )
            self.assertEqual(
                scope.root_cause_groups,
                (
                    ("pricing.py", ("pricing_test.py",)),
                    ("stock.py", ("stock_test.py",)),
                ),
            )

    def test_natural_flow_reports_groups_and_keeps_tests_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            workflow = ScopedWorkflow()
            coordinator = NaturalLanguageImprovementCoordinator(
                workflow,
                self._resolver(root),
                runtime_repair_enabled=True,
            )

            report = coordinator.resolve(
                "ajan: pricing_test.py ve stock_test.py testlerini sandbox içinde çalıştır, "
                "hataları kök nedene göre grupla ve düzelt"
            )

            paths, objective, validation_paths = workflow.prepared[0]
            self.assertEqual(paths, ("pricing.py", "stock.py"))
            self.assertEqual(validation_paths, ("pricing_test.py", "stock_test.py"))
            self.assertIn("Kök neden grupları:", report)
            self.assertIn("pricing.py: pricing_test.py", report)
            self.assertIn("Test sözleşmelerini değiştirmeden", objective)

    def test_multiple_tests_can_share_one_root_cause_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            (root / "pricing_edge_test.py").write_text(
                "import unittest\nfrom pricing import TAX_RATE\n\n"
                "class PricingEdgeTests(unittest.TestCase):\n"
                "    def test_tax_nonzero(self):\n        self.assertGreater(TAX_RATE, 0)\n",
                encoding="utf-8",
            )

            scope = self._resolver(root).resolve_runtime_repair(
                "pricing_test.py ve pricing_edge_test.py testlerini çalıştır ve düzelt"
            )

            self.assertEqual(scope.paths, ("pricing.py",))
            self.assertEqual(
                scope.root_cause_groups,
                (("pricing.py", ("pricing_test.py", "pricing_edge_test.py")),),
            )

    def test_batch_request_is_rejected_when_feature_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)

            with self.assertRaisesRegex(ValueError, "tekil bir test"):
                self._resolver(root, batch=False).resolve_runtime_repair(
                    "pricing_test.py ve stock_test.py testlerini çalıştır ve düzelt"
                )


class BatchEvaluationLimitTests(unittest.TestCase):
    def test_v180_internal_evaluation_accepts_twelve_bounded_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = tuple(f"source_{index}.py" for index in range(9))
            for path in paths:
                (root / path).write_text("VALUE = 1\n", encoding="utf-8")

            report = EvidenceEvaluator(root, UnusedExecutor(), max_paths=12).evaluate(paths)

            self.assertEqual(report.paths, paths)
            with self.assertRaisesRegex(ValueError, "1–8"):
                EvidenceEvaluator(root, UnusedExecutor()).evaluate(paths)


class BatchReadOnlyTestRunTests(unittest.TestCase):
    def test_general_agent_runs_and_reports_every_explicit_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ("pricing_test.py", "stock_test.py"):
                (root / path).write_text(
                    "import unittest\nclass SampleTests(unittest.TestCase):\n"
                    "    def test_value(self):\n        self.assertTrue(True)\n",
                    encoding="utf-8",
                )
            sandbox = PassingSandboxExecutor()
            workspace = ReadOnlyWorkspace(root)
            registry = ToolRegistry(
                (
                    ReadFileTool(workspace),
                    CodeSearchTool(SafeCodeIndex(root)),
                    TargetedSandboxTestTool(root, sandbox),
                )
            )
            executor = ToolExecutor(
                registry,
                RiskBasedToolPolicy((ToolRisk.SAFE, ToolRisk.READ_ONLY, ToolRisk.EXECUTION)),
            )

            report = ReadOnlyToolAgent(UnusedModel(), registry, executor).run(
                "pricing_test.py ve stock_test.py testlerini sandbox içinde çalıştır ve sonucu açıkla"
            )

            self.assertEqual(len(sandbox.commands), 2)
            self.assertIn("2 test dosyası", report)
            self.assertIn("`pricing_test.py`: GEÇTİ", report)
            self.assertIn("`stock_test.py`: GEÇTİ", report)
            self.assertIn("Genel durum: GEÇTİ", report)


class ReleaseV180Tests(unittest.TestCase):
    def test_batch_runtime_repair_requires_single_repair_flow(self):
        with self.assertRaisesRegex(ValueError, "tekli onarım"):
            main_v170.build_application(batch_runtime_repair_enabled=True)

    def test_default_release_enables_batch_runtime_repair(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release(), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V1.8")
            self.assertTrue(flags["runtime_repair_enabled"])
            self.assertTrue(flags["batch_runtime_repair_enabled"])


if __name__ == "__main__":
    unittest.main()
