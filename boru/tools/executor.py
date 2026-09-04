from boru.tools.arguments import (
    ToolArgumentSchema,
    ToolArgumentValidator,
)
from boru.tools.contracts import (
    Tool,
    ToolPolicy,
    ToolRegistryPort,
)
from boru.tools.models import (
    ToolCall,
    ToolResult,
)


class ToolExecutor:
    """Registry, policy ve merkezi argüman doğrulaması üzerinden tool çalıştırır."""

    def __init__(
        self,
        registry: ToolRegistryPort,
        policy: ToolPolicy,
        argument_validator: (
            ToolArgumentValidator
            | None
        ) = None,
    ):
        self._registry = registry
        self._policy = policy
        self._argument_validator = (
            argument_validator
            or ToolArgumentValidator()
        )

    def execute(
        self,
        call: ToolCall,
    ) -> ToolResult:
        tool = self._registry.get(
            call.tool_name
        )

        if tool is None:
            return ToolResult(
                tool_name=(
                    call.tool_name
                ),
                success=False,
                error=(
                    "İstenen tool kayıtlı değil."
                ),
            )

        if not self._policy.is_allowed(
            tool
        ):
            return ToolResult(
                tool_name=(
                    call.tool_name
                ),
                success=False,
                error=(
                    "Bu tool mevcut güvenlik "
                    "politikası tarafından engellendi."
                ),
            )

        try:
            validated_arguments = (
                self
                ._argument_validator
                .validate(
                    self._argument_schema_for(
                        tool
                    ),
                    call.arguments,
                )
            )

        except Exception as error:
            return ToolResult(
                tool_name=(
                    call.tool_name
                ),
                success=False,
                error=(
                    "Tool argümanları geçersiz: "
                    f"{error}"
                ),
            )

        try:
            result = tool.execute(
                validated_arguments
            )

        except Exception as error:
            return ToolResult(
                tool_name=(
                    call.tool_name
                ),
                success=False,
                error=(
                    "Tool güvenli biçimde "
                    "çalıştırılamadı: "
                    f"{error}"
                ),
            )

        if (
            result.tool_name
            != tool.name
        ):
            return ToolResult(
                tool_name=(
                    call.tool_name
                ),
                success=False,
                error=(
                    "Tool sonucu beklenen tool "
                    "adıyla eşleşmiyor."
                ),
            )

        return result

    @staticmethod
    def _argument_schema_for(
        tool: Tool,
    ) -> ToolArgumentSchema:
        schema = getattr(
            tool,
            "argument_schema",
            None,
        )

        if schema is None:
            return ToolArgumentSchema()

        if not isinstance(
            schema,
            ToolArgumentSchema,
        ):
            raise TypeError(
                f"{tool.name} geçerli bir "
                "ToolArgumentSchema sağlamıyor."
            )

        return schema