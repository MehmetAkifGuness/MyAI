import tempfile
import unittest
from pathlib import Path

from boru.code_index.graph import ProjectDependencyGraph
from boru.code_index.graph_coordinator import DependencyGraphCoordinator
from boru.nlu.intent_router import FreeFormIntentRouter, RoutedIntent


class DependencyGraphTests(unittest.TestCase):
    def test_analyzes_forward_and_reverse_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pkg = root / "app"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "core.py").write_text("def engine(): return 1\n", encoding="utf-8")
            (pkg / "service.py").write_text("from app.core import engine\ndef run(): return engine()\n", encoding="utf-8")

            t_dir = root / "tests"
            t_dir.mkdir()
            (t_dir / "test_service.py").write_text("import app.service\n", encoding="utf-8")

            graph = ProjectDependencyGraph(root)

            # core.py analizi
            core_rep = graph.analyze_file("app/core.py")
            self.assertIn("app/service.py", core_rep.reverse_dependents)

            # service.py analizi
            svc_rep = graph.analyze_file("app/service.py")
            self.assertIn("app/core.py", svc_rep.forward_imports)
            self.assertIn("tests/test_service.py", svc_rep.associated_tests)

    def test_find_symbol_references(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tools.py").write_text("def compute(): return 42\n", encoding="utf-8")
            (root / "main.py").write_text("from tools import compute\nx = compute()\n", encoding="utf-8")

            graph = ProjectDependencyGraph(root)
            refs = graph.find_symbol_references("compute")

            self.assertTrue(any(r.kind == "tanım" and r.path == "tools.py" for r in refs))
            self.assertTrue(any(r.kind == "import" and r.path == "main.py" for r in refs))
            self.assertTrue(any(r.kind == "kullanım" and r.path == "main.py" for r in refs))

    def test_plan_symbol_rename_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "math_lib.py").write_text("def calculate_sum(a, b):\n    return a + b\n", encoding="utf-8")
            (root / "client.py").write_text("from math_lib import calculate_sum\nres = calculate_sum(1, 2)\n", encoding="utf-8")

            graph = ProjectDependencyGraph(root)
            coord = DependencyGraphCoordinator(root, graph)

            # Plan oluştur
            plan_output = coord.resolve("yeniden adlandır: math_lib.py | calculate_sum -> add_numbers")
            self.assertIsNotNone(plan_output)
            self.assertIn("ÇOKLU DOSYA REFACTOR PLANI", plan_output)
            self.assertIn("Etkilenen Dosyalar: 2 adet", plan_output)

            # Onayla ve uygula
            apply_output = coord.resolve("refactor onayla")
            self.assertIn("REFACTOR BAŞARIYLA UYGULANDI", apply_output)

            # İçerik kontrolü
            math_content = (root / "math_lib.py").read_text(encoding="utf-8")
            client_content = (root / "client.py").read_text(encoding="utf-8")

            self.assertIn("def add_numbers(a, b):", math_content)
            self.assertIn("from math_lib import add_numbers", client_content)
            self.assertIn("res = add_numbers(1, 2)", client_content)


class DependencyCoordinatorTests(unittest.TestCase):
    def test_handles_dependencies_and_symbol_search(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "a.py").write_text("class MyEngine:\n    pass\n", encoding="utf-8")
            (root / "b.py").write_text("from a import MyEngine\n", encoding="utf-8")

            coord = DependencyGraphCoordinator(root)

            dep_res = coord.resolve("bağımlılıklar: a.py")
            self.assertIn("BAĞIMLILIK VE ETKİ HARİTASI", dep_res)
            self.assertIn("b.py", dep_res)

            sym_res = coord.resolve("sembol ara: MyEngine")
            self.assertIn("SEMBOL ARAMA RAPORU", sym_res)
            self.assertIn("a.py", sym_res)
            self.assertIn("b.py", sym_res)


class IntentRouterDependencyTests(unittest.TestCase):
    def setUp(self):
        self.router = FreeFormIntentRouter()

    def test_routes_dependency_request(self):
        res = self.router.route("boru/nlu/fuzzy_matcher.py bağımlılıklarını göster")
        self.assertEqual(res.intent, RoutedIntent.DEPENDENCY)
        self.assertEqual(res.transformed_message, "bağımlılıklar: boru/nlu/fuzzy_matcher.py")

    def test_routes_symbol_search_request(self):
        res = self.router.route("normalize_turkish sembolünü ara")
        self.assertEqual(res.intent, RoutedIntent.SYMBOL_SEARCH)
        self.assertEqual(res.transformed_message, "sembol ara: normalize_turkish")


if __name__ == "__main__":
    unittest.main()

