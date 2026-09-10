"""
boru.tools.ast_editor
=====================
Python kodlarını Abstract Syntax Tree (AST) seviyesinde inceleyen,
fonksiyon/sınıf bazlı nokta atışı hedef tespiti ve otomatik sözdizimi
onarımını (self-healing syntax guard) sağlayan semantik düzenleme motoru.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TargetSymbolRange:
    name: str
    kind: str  # 'function', 'class', 'method'
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    source_segment: str


class AstSemanticEditor:
    """
    Python kaynak kodunu AST üzerinden analiz eder ve sözdizimsel
    bütünlüğü koruyarak cerrahi semantik düzenlemeler gerçekleştirir.
    """

    @staticmethod
    def parse_safe(content: str, filename: str = "<source>") -> ast.AST | None:
        """Kodu güvenle ayrıştırır, hata varsa None döner."""
        try:
            return ast.parse(content, filename=filename)
        except SyntaxError:
            return None

    @classmethod
    def find_symbol(cls, source_code: str, symbol_name: str) -> TargetSymbolRange | None:
        """
        Kaynak kod içinde verilen fonksiyon veya sınıf adını AST seviyesinde bulur
        ve satır aralığını döndürür.
        """
        tree = cls.parse_safe(source_code)
        if tree is None:
            return None

        lines = source_code.splitlines(keepends=True)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol_name:
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    start_line = node.lineno
                    end_line = getattr(node, "end_lineno", start_line)
                    start_col = node.col_offset
                    end_col = getattr(node, "end_col_offset", 0)

                    # İlgili satırları birleştir
                    segment_lines = lines[start_line - 1 : end_line]
                    segment = "".join(segment_lines)

                    return TargetSymbolRange(
                        name=symbol_name,
                        kind=kind,
                        start_line=start_line,
                        end_line=end_line,
                        start_col=start_col,
                        end_col=end_col,
                        source_segment=segment,
                    )

        return None

    @classmethod
    def replace_symbol(cls, source_code: str, symbol_name: str, new_symbol_code: str) -> str:
        """
        Hedef fonksiyon veya sınıfı AST sınırlarına göre tam olarak yenisiyle değiştirir.
        """
        target = cls.find_symbol(source_code, symbol_name)
        if target is None:
            raise ValueError(f"'{symbol_name}' sembolü AST ağacında bulunamadı.")

        lines = source_code.splitlines(keepends=True)
        # Hedef bloğun öncesi ve sonrası
        before = "".join(lines[: target.start_line - 1])
        after = "".join(lines[target.end_line :])

        # Yeni kodun sonunda newline yoksa koru
        replacement = new_symbol_code
        if not replacement.endswith("\n") and (after or target.source_segment.endswith("\n")):
            replacement += "\n"

        result = before + replacement + after

        # Self-healing sözdizim kontrolü
        if not cls.verify_syntax(result):
            raise SyntaxError(f"'{symbol_name}' değiştirildikten sonra oluşan kod geçerli bir Python AST oluşturmadı.")

        return result

    @classmethod
    def verify_syntax(cls, code: str) -> bool:
        """Kodun geçerli ve derlenebilir Python kodu olduğunu doğrular."""
        try:
            ast.parse(code)
            compile(code, "<verify>", "exec")
            return True
        except (SyntaxError, ValueError):
            return False

    @classmethod
    def attempt_self_heal(cls, broken_code: str) -> str:
        """
        Basit sözdizimi ve girinti hatalarını (eksik iki nokta, kapanmamış parantez vb.)
        kendi kendine iyileştirmeyi dener.
        """
        if cls.verify_syntax(broken_code):
            return broken_code

        # Deneme 1: Eksik iki nokta üst üste (def/class/if/for/while satırlarının sonunda)
        fixed_lines = []
        for line in broken_code.splitlines(keepends=True):
            stripped = line.rstrip()
            if (
                any(stripped.lstrip().startswith(kw) for kw in ("def ", "class ", "if ", "elif ", "else:", "for ", "while ", "try:", "except", "finally:"))
                and not stripped.endswith(":")
                and not stripped.endswith("\\")
            ):
                line = stripped + ":\n"
            fixed_lines.append(line)

        candidate = "".join(fixed_lines)
        if cls.verify_syntax(candidate):
            return candidate

        # Deneme 2: Eksik kapanış parantezi
        open_parens = broken_code.count("(") - broken_code.count(")")
        open_brackets = broken_code.count("[") - broken_code.count("]")
        open_braces = broken_code.count("{") - broken_code.count("}")

        patch = candidate.rstrip()
        if open_parens > 0:
            patch += ")" * open_parens
        if open_brackets > 0:
            patch += "]" * open_brackets
        if open_braces > 0:
            patch += "}" * open_braces
        patch += "\n"

        if cls.verify_syntax(patch):
            return patch

        # İyileştirilemediyse orijinali koru
        return broken_code
