from boru.tools.contracts import (
    ToolPolicy,
    ToolRegistryPort,
)
from boru.tools.models import (
    ToolCall,
    ToolResult,
)


class ToolExecutor:
    """Tool çağrılarının registry ve policy sınırından geçmesini sağlar."""

    def __init__(
        self,
        registry: ToolRegistryPort,
        policy: ToolPolicy,
    ):
        self._registry = registry
        self._policy = policy

    def execute(
        self,
        call: ToolCall,
    ) -> ToolResult:
        tool = self._registry.get(
            call.tool_name
        )

        if tool is None:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=(
                    "İstenen tool kayıtlı değil."
                ),
            )

        if not self._policy.is_allowed(tool):
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=(
                    "Bu tool mevcut güvenlik politikası "
                    "tarafından engellendi."
                ),
            )

        try:
            result = tool.execute(
                dict(call.arguments)
            )
        except Exception as error:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=(
                    "Tool güvenli biçimde çalıştırılamadı: "
                    f"{error}"
                ),
            )

        if result.tool_name != tool.name:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=(
                    "Tool sonucu beklenen tool adıyla eşleşmiyor."
                ),
            )

        return result