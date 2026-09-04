from boru.tools.contracts import (
    ToolExecutorPort,
    ToolPlanner,
    ToolResultSynthesizer,
)
from boru.tools.models import (
    ToolResponseMode,
)


class ToolCoordinator:
    """Tek-tool planlama, çalıştırma ve isteğe bağlı sentezi yönetir."""

    def __init__(
        self,
        planner: ToolPlanner,
        executor: ToolExecutorPort,
        synthesizer: ToolResultSynthesizer | None = None,
    ):
        self._planner = planner
        self._executor = executor
        self._synthesizer = synthesizer

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

        if not result.success:
            return (
                "Aracı çalıştıramadım: "
                f"{result.error}"
            )

        cleaned = result.content.strip()
        if not cleaned:
            raise RuntimeError(
                "Tool başarılı ancak boş sonuç döndürdü."
            )

        if decision.response_mode is ToolResponseMode.DIRECT:
            return cleaned

        if self._synthesizer is None:
            raise RuntimeError(
                "Tool sonucu sentezlenmek istendi ancak synthesizer yapılandırılmadı."
            )

        return self._synthesizer.synthesize(
            user_message=user_message,
            instruction=decision.synthesis_instruction,
            tool_call=decision.tool_call,
            tool_result=result,
        )