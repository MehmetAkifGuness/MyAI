import ast
import math
import operator
from collections.abc import Callable

from boru.tools.models import (
    ToolResult,
    ToolRisk,
)


class CalculatorTool:
    """Sınırlı AST yorumlama ile temel aritmetik hesaplar."""

    _BINARY_OPERATORS: dict[
        type[ast.operator],
        Callable[[float, float], float],
    ] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    _UNARY_OPERATORS: dict[
        type[ast.unaryop],
        Callable[[float], float],
    ] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    _MAX_AST_NODES = 64
    _MAX_ABS_LITERAL = 1_000_000_000_000
    _MAX_ABS_RESULT = 1e100
    _MAX_ABS_EXPONENT = 12

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return (
            "Temel aritmetik ifadeleri güvenli biçimde hesaplar."
        )

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.SAFE

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        expression = arguments.get(
            "expression"
        )

        if not isinstance(expression, str):
            raise ValueError(
                "'expression' metin olmalıdır."
            )

        cleaned = expression.strip()
        if not cleaned:
            raise ValueError(
                "Hesaplanacak ifade boş olamaz."
            )

        try:
            tree = ast.parse(
                cleaned,
                mode="eval",
            )
        except SyntaxError as error:
            raise ValueError(
                "Geçersiz aritmetik ifade."
            ) from error

        if sum(1 for _ in ast.walk(tree)) > self._MAX_AST_NODES:
            raise ValueError(
                "Aritmetik ifade çok karmaşık."
            )

        value = self._evaluate(
            tree.body
        )

        if not math.isfinite(float(value)):
            raise ValueError(
                "Hesap sonucu sonlu bir sayı değil."
            )

        if abs(float(value)) > self._MAX_ABS_RESULT:
            raise ValueError(
                "Hesap sonucu izin verilen sınırı aşıyor."
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            content=self._format_number(
                value
            ),
        )

    def _evaluate(
        self,
        node: ast.AST,
    ) -> int | float:
        if isinstance(node, ast.Constant):
            value = node.value

            if isinstance(value, bool) or not isinstance(
                value,
                (int, float),
            ):
                raise ValueError(
                    "Yalnızca sayısal sabitlere izin verilir."
                )

            if abs(value) > self._MAX_ABS_LITERAL:
                raise ValueError(
                    "Sayısal değer izin verilen sınırı aşıyor."
                )

            return value

        if isinstance(node, ast.UnaryOp):
            operator_function = self._UNARY_OPERATORS.get(
                type(node.op)
            )

            if operator_function is None:
                raise ValueError(
                    "Desteklenmeyen tekli operatör."
                )

            return operator_function(
                self._evaluate(node.operand)
            )

        if isinstance(node, ast.BinOp):
            operator_function = self._BINARY_OPERATORS.get(
                type(node.op)
            )

            if operator_function is None:
                raise ValueError(
                    "Desteklenmeyen aritmetik operatör."
                )

            left = self._evaluate(
                node.left
            )
            right = self._evaluate(
                node.right
            )

            if (
                isinstance(node.op, ast.Pow)
                and abs(right) > self._MAX_ABS_EXPONENT
            ):
                raise ValueError(
                    "Üs değeri izin verilen sınırı aşıyor."
                )

            try:
                result = operator_function(
                    left,
                    right,
                )
            except (
                ArithmeticError,
                OverflowError,
            ) as error:
                raise ValueError(
                    "Aritmetik işlem tamamlanamadı."
                ) from error

            if not isinstance(result, (int, float)):
                raise ValueError(
                    "Geçersiz aritmetik sonuç."
                )

            if abs(float(result)) > self._MAX_ABS_RESULT:
                raise ValueError(
                    "Ara sonuç izin verilen sınırı aşıyor."
                )

            return result

        raise ValueError(
            "İfadede izin verilmeyen bir yapı var."
        )

    @staticmethod
    def _format_number(
        value: int | float,
    ) -> str:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))

        return str(value)