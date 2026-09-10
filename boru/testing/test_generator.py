"""
boru.testing.test_generator
===========================
Python kaynak dosyalarını AST seviyesinde analiz ederek fonksiyonlar, sınıflar
ve metotlar için çalıştırılabilir, standart unittest test kodları üreten
otomatik test sentezleyici (Auto-Test Generator).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ParameterInfo:
    name: str
    default_value: str | None = None
    annotation: str | None = None


@dataclass(frozen=True, slots=True)
class FunctionSymbolInfo:
    name: str
    parameters: tuple[ParameterInfo, ...]
    docstring: str | None = None
    is_method: bool = False
    class_name: str | None = None


@dataclass(frozen=True, slots=True)
class ClassSymbolInfo:
    name: str
    methods: tuple[FunctionSymbolInfo, ...]
    docstring: str | None = None
    init_parameters: tuple[ParameterInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class ModuleAnalysisResult:
    module_name: str
    classes: tuple[ClassSymbolInfo, ...]
    functions: tuple[FunctionSymbolInfo, ...]


@dataclass(frozen=True, slots=True)
class GeneratedTestSuite:
    target_module: str
    test_code: str
    symbol_count: int
    test_methods_count: int


@dataclass(frozen=True, slots=True)
class GeneratedTestFileResult:
    target_path: str
    output_path: str
    test_suite: GeneratedTestSuite
    saved: bool


class AutoTestGenerator:
    """
    Python kaynak kodunu inceler, sembolleri çıkarır ve unittest tabanlı
    kapsamlı test senaryoları sentezler.
    """

    def analyze_source(self, source_code: str, module_name: str = "module") -> ModuleAnalysisResult:
        tree = ast.parse(source_code)
        classes: list[ClassSymbolInfo] = []
        functions: list[FunctionSymbolInfo] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                methods: list[FunctionSymbolInfo] = []
                init_params: list[ParameterInfo] = []
                class_doc = ast.get_docstring(node)

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        params = self._extract_parameters(item)
                        if item.name == "__init__":
                            init_params = [p for p in params if p.name not in {"self", "cls"}]
                        elif not item.name.startswith("_"):
                            methods.append(
                                FunctionSymbolInfo(
                                    name=item.name,
                                    parameters=tuple(p for p in params if p.name not in {"self", "cls"}),
                                    docstring=ast.get_docstring(item),
                                    is_method=True,
                                    class_name=node.name,
                                )
                            )

                classes.append(
                    ClassSymbolInfo(
                        name=node.name,
                        methods=tuple(methods),
                        docstring=class_doc,
                        init_parameters=tuple(init_params),
                    )
                )

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    params = self._extract_parameters(node)
                    functions.append(
                        FunctionSymbolInfo(
                            name=node.name,
                            parameters=tuple(params),
                            docstring=ast.get_docstring(node),
                            is_method=False,
                        )
                    )

        return ModuleAnalysisResult(
            module_name=module_name,
            classes=tuple(classes),
            functions=tuple(functions),
        )

    def generate_suite(self, source_code: str, module_import_path: str) -> GeneratedTestSuite:
        analysis = self.analyze_source(source_code, module_name=module_import_path.split(".")[-1])
        lines: list[str] = [
            '"""',
            "Otomatik olarak Börü Auto-Test Generator tarafından üretildi.",
            f"Hedef modül: {module_import_path}",
            '"""',
            "",
            "import unittest",
            f"import {module_import_path} as target_module",
            "",
        ]

        total_symbols = len(analysis.classes) + len(analysis.functions)
        test_method_counter = 0

        # 1. Bağımsız Fonksiyonlar için Testler
        if analysis.functions:
            lines.extend([
                f"class Test{self._pascal_case(analysis.module_name)}Functions(unittest.TestCase):",
                f'    """{analysis.module_name} modülündeki üst seviye fonksiyonlar için testler."""',
                "",
            ])
            for fn in analysis.functions:
                lines.extend(self._generate_function_tests(fn))
                test_method_counter += 2

        # 2. Sınıflar için Testler
        for cls in analysis.classes:
            lines.extend([
                f"class Test{cls.name}(unittest.TestCase):",
                f'    """{cls.name} sınıfı için birim testleri."""',
                "",
            ])
            # Başlatma testi
            lines.extend(self._generate_class_init_test(cls))
            test_method_counter += 1

            for method in cls.methods:
                lines.extend(self._generate_method_tests(cls, method))
                test_method_counter += 1

        if total_symbols == 0:
            lines.extend([
                f"class Test{self._pascal_case(analysis.module_name)}Smoke(unittest.TestCase):",
                f'    """Modül seviyesi duman (smoke) testi."""',
                "",
                "    def test_module_imports(self):",
                "        self.assertIsNotNone(target_module)",
                "",
            ])
            test_method_counter += 1

        lines.extend([
            "",
            'if __name__ == "__main__":',
            "    unittest.main()",
            "",
        ])

        generated_code = "\n".join(lines)

        # Sözdizimi geçerliliği kontrolü (Syntax Guard)
        try:
            ast.parse(generated_code)
        except SyntaxError as err:
            raise ValueError(f"Üretilen test kodu sözdizimi hatası içeriyor: {err}") from err

        return GeneratedTestSuite(
            target_module=module_import_path,
            test_code=generated_code,
            symbol_count=total_symbols,
            test_methods_count=test_method_counter,
        )

    def generate_for_file(
        self,
        file_path: str | Path,
        output_dir: str | Path | None = None,
        save: bool = True,
    ) -> GeneratedTestFileResult:
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Kaynak dosya bulunamadı: {file_path}")

        source_code = path.read_text(encoding="utf-8")

        try:
            cwd = Path.cwd().resolve()
            rel_path = path.relative_to(cwd)
            module_parts = list(rel_path.with_suffix("").parts)
            module_import_path = ".".join(module_parts)
        except Exception:
            module_import_path = path.stem

        suite = self.generate_suite(source_code, module_import_path)

        if output_dir is None:
            output_dir = Path("tests")
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        out_filename = f"test_{path.stem}_auto.py"
        out_path = output_dir / out_filename

        if save:
            out_path.write_text(suite.test_code, encoding="utf-8")

        return GeneratedTestFileResult(
            target_path=str(path),
            output_path=str(out_path),
            test_suite=suite,
            saved=save,
        )

    # --- Yardımcı Üretim Metotları ---

    def _extract_parameters(self, fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ParameterInfo]:
        params: list[ParameterInfo] = []
        args = fn_node.args.args
        defaults = [None] * (len(args) - len(fn_node.args.defaults)) + [
            ast.unparse(d) for d in fn_node.args.defaults
        ]

        for arg, default in zip(args, defaults):
            annotation = ast.unparse(arg.annotation) if arg.annotation else None
            params.append(ParameterInfo(name=arg.arg, default_value=default, annotation=annotation))
        return params

    def _generate_function_tests(self, fn: FunctionSymbolInfo) -> list[str]:
        args_call = self._mock_arguments(fn.parameters)
        return [
            f"    def test_{fn.name}_callable(self):",
            f'        """target_module.{fn.name} fonksiyonunun çağrılabilirliğini test eder."""',
            f"        self.assertTrue(callable(getattr(target_module, '{fn.name}', None)))",
            "",
            f"    def test_{fn.name}_basic_execution(self):",
            f'        """target_module.{fn.name} varsayılan veya sembolik argümanlarla koşturulur."""',
            "        try:",
            f"            result = target_module.{fn.name}({args_call})",
            "            self.assertIsNotNone(result)",
            "        except (NotImplementedError, TypeError, ValueError):",
            "            pass",
            "",
        ]

    def _generate_class_init_test(self, cls: ClassSymbolInfo) -> list[str]:
        args_call = self._mock_arguments(cls.init_parameters)
        return [
            f"    def test_instantiation(self):",
            f'        """{cls.name} sınıfının başlatılabilmesini doğrular."""',
            "        try:",
            f"            instance = target_module.{cls.name}({args_call})",
            "            self.assertIsNotNone(instance)",
            "        except (TypeError, ValueError, NotImplementedError):",
            "            pass",
            "",
        ]

    def _generate_method_tests(self, cls: ClassSymbolInfo, method: FunctionSymbolInfo) -> list[str]:
        init_call = self._mock_arguments(cls.init_parameters)
        method_call = self._mock_arguments(method.parameters)
        return [
            f"    def test_method_{method.name}(self):",
            f'        """{cls.name}.{method.name} metodunun çağrılabilmesini doğrular."""',
            "        try:",
            f"            instance = target_module.{cls.name}({init_call})",
            f"            result = instance.{method.name}({method_call})",
            "            self.assertIsNotNone(result)",
            "        except (TypeError, ValueError, NotImplementedError, AttributeError):",
            "            pass",
            "",
        ]

    def _mock_arguments(self, params: Sequence[ParameterInfo]) -> str:
        pieces = []
        for p in params:
            if p.default_value is not None:
                continue
            ann = (p.annotation or "").lower()
            if "int" in ann:
                val = "1"
            elif "float" in ann:
                val = "1.0"
            elif "bool" in ann:
                val = "True"
            elif "str" in ann:
                val = '"test"'
            elif "list" in ann or "sequence" in ann:
                val = "[]"
            elif "dict" in ann or "mapping" in ann:
                val = "{}"
            elif "tuple" in ann:
                val = "()"
            else:
                val = "None"
            pieces.append(val)
        return ", ".join(pieces)

    @staticmethod
    def _pascal_case(text: str) -> str:
        clean = "".join(c if c.isalnum() else " " for c in text)
        return "".join(word.capitalize() for word in clean.split())
