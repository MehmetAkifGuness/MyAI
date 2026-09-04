from collections.abc import Iterable

from boru.tools.contracts import Tool
from boru.tools.models import ToolRisk


class RiskBasedToolPolicy:
    """Yalnızca açıkça izin verilen risk sınıflarındaki tool'ları çalıştırır."""

    def __init__(
        self,
        allowed_risks: Iterable[ToolRisk] = (
            ToolRisk.SAFE,
        ),
    ):
        self._allowed_risks = frozenset(
            allowed_risks
        )

    def is_allowed(
        self,
        tool: Tool,
    ) -> bool:
        return (
            tool.risk
            in self._allowed_risks
        )