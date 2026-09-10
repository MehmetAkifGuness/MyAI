import unittest

from boru.tools.ast_editor import AstSemanticEditor


class AstSemanticEditorTests(unittest.TestCase):
    def test_find_symbol_function_and_class(self):
        sample_code = """
import os

def calculate_sum(a: int, b: int) -> int:
    # Toplama fonksiyonu
    return a + b

class MathProcessor:
    def multiply(self, x, y):
        return x * y
"""
        func_range = AstSemanticEditor.find_symbol(sample_code, "calculate_sum")
        self.assertIsNotNone(func_range)
        self.assertEqual(func_range.name, "calculate_sum")
        self.assertEqual(func_range.kind, "function")
        self.assertIn("return a + b", func_range.source_segment)

        class_range = AstSemanticEditor.find_symbol(sample_code, "MathProcessor")
        self.assertIsNotNone(class_range)
        self.assertEqual(class_range.name, "MathProcessor")
        self.assertEqual(class_range.kind, "class")
        self.assertIn("def multiply", class_range.source_segment)

    def test_replace_symbol_exact_ast_boundaries(self):
        sample_code = """def hello():
    return 'hello'

def world():
    return 'world'
"""
        new_hello = """def hello(name: str = 'user'):
    return f'hello {name}'"""

        updated = AstSemanticEditor.replace_symbol(sample_code, "hello", new_hello)
        self.assertIn("def hello(name: str = 'user'):", updated)
        self.assertIn("def world():", updated)
        self.assertTrue(AstSemanticEditor.verify_syntax(updated))

    def test_verify_syntax(self):
        valid = "def foo(): pass"
        invalid = "def foo() pass"
        self.assertTrue(AstSemanticEditor.verify_syntax(valid))
        self.assertFalse(AstSemanticEditor.verify_syntax(invalid))

    def test_attempt_self_heal_missing_colon(self):
        broken = "def my_func(a, b)\n    return a + b"
        healed = AstSemanticEditor.attempt_self_heal(broken)
        self.assertTrue(AstSemanticEditor.verify_syntax(healed))
        self.assertIn("def my_func(a, b):", healed)

    def test_attempt_self_heal_missing_parenthesis(self):
        broken = "print(int(10 + 20"
        healed = AstSemanticEditor.attempt_self_heal(broken)
        self.assertTrue(AstSemanticEditor.verify_syntax(healed))


if __name__ == "__main__":
    unittest.main()
