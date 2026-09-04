from boru.tools.contracts import (
    ToolExecutorPort,
    ToolPlanner,
)


class ToolCoordinator:
    """Tool planlama ve çalıştırmayı AssistantService'ten ayrı tutar."""

    def __init__(
        self,
        planner: ToolPlanner,
        executor: ToolExecutorPort,
    ):
        self._planner = planner
        self._executor = executor

    def resolve(
        self,
        user_message: str,
    ) -> str | None:
        decision = self._planner.plan(
            user_message
        )

        if not decision.should_use_tool:
            return None

        if decision.tool_call is None:
            raise RuntimeError(
                "Tool planner geçersiz karar döndürdü."
            )

        result = self._executor.execute(
            decision.tool_call
        )

        if result.success:
            cleaned = result.content.strip()
            if not cleaned:
                raise RuntimeError(
                    "Tool başarılı ancak boş sonuç döndürdü."
                )
            return cleaned

        return (
            "Aracı çalıştıramadım: "
            f"{result.error}"
        )