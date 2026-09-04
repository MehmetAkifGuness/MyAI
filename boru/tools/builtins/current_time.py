from collections.abc import (
    Callable,
)
from datetime import datetime

from boru.tools.arguments import (
    ToolArgumentSchema,
)
from boru.tools.models import (
    ToolResult,
    ToolRisk,
)


class CurrentTimeTool:
    """Çalışılan sistemin yerel tarih ve saatini döndürür."""

    def __init__(
        self,
        clock: (
            Callable[
                [],
                datetime,
            ]
            | None
        ) = None,
    ):
        self._clock = (
            clock
            or (
                lambda:
                datetime
                .now()
                .astimezone()
            )
        )

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(
        self,
    ) -> str:
        return (
            "Sistemin geçerli yerel "
            "tarih ve saatini döndürür. "
            "Argüman almaz."
        )

    @property
    def risk(
        self,
    ) -> ToolRisk:
        return ToolRisk.SAFE

    @property
    def argument_schema(
        self,
    ) -> ToolArgumentSchema:
        return ToolArgumentSchema()

    def execute(
        self,
        arguments: dict[
            str,
            object,
        ],
    ) -> ToolResult:
        if arguments:
            raise ValueError(
                "get_current_time "
                "argüman kabul etmez."
            )

        current = self._clock()

        if current.tzinfo is None:
            current = (
                current.astimezone()
            )

        offset = (
            current.strftime(
                "%z"
            )
        )

        formatted_offset = (
            f"{offset[:3]}:{offset[3:]}"
            if offset
            else "yerel"
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            content=(
                "Yerel tarih ve saat: "
                f"{current:%d.%m.%Y %H:%M:%S} "
                f"({formatted_offset})"
            ),
        )