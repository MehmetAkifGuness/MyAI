import ast
import tempfile
import unittest
from pathlib import Path

from boru.nlu.intent_router import FreeFormIntentRouter, RoutedIntent
from boru.testing.generator_coordinator import AutoTestGeneratorCoordinator
from boru.testing.test_generator import AutoTestGenerator


class AutoTestGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.generator = AutoTestGenerator()

    def test_analyzes_classes_and_functions(self):
        sample_code = '''
def add(a: int, b: int = 0) -> int:
    """İki sayıyı toplar."""
    return a + b

class Calculator:
    """Basit hesap makinesi."""
    def __init__(self, precision: int = 2):
        self.precision = precision

    def multiply(self, x: float, y: float) -> float:
        return x * y
'''
        analysis = self.generator.analyze_source(sample_code, module_name="calc")
        self.assertEqual(len(analysis.functions), 1)
        self.assertEqual(analysis.functions[0].name, "add")
        self.assertEqual(len(analysis.classes), 1)
        self.assertEqual(analysis.classes[0].name, "Calculator")
        self.assertEqual(len(analysis.classes[0].methods), 1)
        self.assertEqual(analysis.classes[0].methods[0].name, "multiply")

    def test_generates_valid_unittest_suite(self):
        sample_code = '''
def process_data(text: str) -> str:
    return text.strip()

class Processor:
    def execute(self, payload: dict) -> bool:
        return True
'''
        suite = self.generator.generate_suite(sample_code, module_import_path="my_app.service")
        self.assertIn("class TestServiceFunctions(unittest.TestCase):", suite.test_code)
        self.assertIn("class TestProcessor(unittest.TestCase):", suite.test_code)
        self.assertIn("def test_process_data_callable(self):", suite.test_code)
        self.assertIn("def test_method_execute(self):", suite.test_code)
        # Sözdizimi geçerliliği
        parsed = ast.parse(suite.test_code)
        self.assertIsNotNone(parsed)

    def test_generate_for_file_writes_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_file = tmp_path / "helper.py"
            source_file.write_text("def ping() -> str:\n    return 'pong'\n", encoding="utf-8")

            out_dir = tmp_path / "out_tests"
            result = self.generator.generate_for_file(source_file, output_dir=out_dir, save=True)

            self.assertTrue(result.saved)
            self.assertTrue(Path(result.output_path).exists())
            content = Path(result.output_path).read_text(encoding="utf-8")
            self.assertIn("test_ping_callable", content)


class AutoTestGeneratorCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = AutoTestGeneratorCoordinator()

    def test_returns_none_for_unrelated_message(self):
        result = self.coordinator.resolve("bugün hava nasıl?")
        self.assertIsNone(result)

    def test_resolves_test_uret_with_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_file = tmp_path / "sample.py"
            source_file.write_text("def run():\n    return 42\n", encoding="utf-8")

            response = self.coordinator.resolve(f"test üret: {source_file}")
            self.assertIsNotNone(response)
            self.assertIn("🧪 OTOMATİK TEST RAPORU", response)
            self.assertIn("Sözdizimi Doğrulaması: GEÇTİ", response)

    def test_reports_error_for_missing_file(self):
        response = self.coordinator.resolve("test üret: non_existent_source_file_xyz.py")
        self.assertIsNotNone(response)
        self.assertIn("❌ Test Üretim Hatası: Belirtilen kaynak dosya bulunamadı", response)

    def test_calls_test_runner_when_calistir_specified(self):
        runner_called = []

        def mock_runner(path: str) -> str:
            runner_called.append(path)
            return "Mock: 2/2 test geçti"

        coord = AutoTestGeneratorCoordinator(test_runner=mock_runner)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_file = tmp_path / "demo.py"
            source_file.write_text("def check(): pass\n", encoding="utf-8")

            response = coord.resolve(f"test üret ve çalıştır: {source_file}")
            self.assertIn("Mock: 2/2 test geçti", response)
            self.assertEqual(len(runner_called), 1)


class IntentRouterTestGenerationTests(unittest.TestCase):
    def setUp(self):
        self.router = FreeFormIntentRouter()

    def test_routes_free_form_test_generation_request(self):
        routed = self.router.route("boru/nlu/fuzzy_matcher.py için test üret")
        self.assertEqual(routed.intent, RoutedIntent.TEST_GENERATION)
        self.assertEqual(routed.transformed_message, "test üret: boru/nlu/fuzzy_matcher.py")

    def test_routes_testlerini_yaz_request(self):
        routed = self.router.route("boru/config.py dosyasının testlerini yaz")
        self.assertEqual(routed.intent, RoutedIntent.TEST_GENERATION)
        self.assertEqual(routed.transformed_message, "test üret: boru/config.py")


if __name__ == "__main__":
    unittest.main()

