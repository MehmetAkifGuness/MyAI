import re
from collections.abc import Iterable

from boru.tools.contracts import Tool
from boru.tools.models import ToolDefinition


class ToolRegistry:
    """Kayıtlı tool'ları isim üzerinden güvenli biçimde çözümler."""

    _NAME_PATTERN = re.compile(
        r"^[a-z][a-z0-9_]*$"
    )

    def __init__(
        self,
        tools: Iterable[Tool] = (),
    ):
        self._tools: dict[str, Tool] = {}

        for tool in tools:
            self.register(tool)

    def register(
        self,
        tool: Tool,
    ) -> None:
        name = tool.name.strip()

        if not self._NAME_PATTERN.fullmatch(name):
            raise ValueError(
                f"Geçersiz tool adı: {name!r}"
            )

        if name in self._tools:
            raise ValueError(
                f"Tool zaten kayıtlı: {name}"
            )

        self._tools[name] = tool

    def get(
        self,
        name: str,
    ) -> Tool | None:
        return self._tools.get(
            name.strip()
        )

    def definitions(
        self,
    ) -> tuple[ToolDefinition, ...]:
        return tuple(
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                risk=tool.risk,
            )
            for tool in self._tools.values()
        )