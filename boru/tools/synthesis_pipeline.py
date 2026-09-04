from collections.abc import Sequence

from boru.tools.contracts import (
    ToolResultSynthesisResolver,
    ToolResultSynthesizer,
)
from boru.tools.models import (
    ToolCall,
    ToolResult,
)


class CompositeToolResultSynthesizer:
    """Deterministik resolver'ları deneyip sonra güvenli fallback senteze geçer."""

    def __init__(
        self,
        *,
        resolvers: Sequence[ToolResultSynthesisResolver] = (),
        fallback: ToolResultSynthesizer,
    ):
        self._resolvers = tuple(
            resolvers
        )
        self._fallback = fallback

    def synthesize(
        self,
        *,
        user_message: str,
        instruction: str,
        tool_call: ToolCall,
        tool_result: ToolResult,
    ) -> str:
        for resolver in self._resolvers:
            response = resolver.resolve(
                user_message=user_message,
                instruction=instruction,
                tool_call=tool_call,
                tool_result=tool_result,
            )

            if response is None:
                continue

            cleaned = response.strip()
            if not cleaned:
                raise RuntimeError(
                    "Deterministik tool sentez resolver'ı boş cevap döndürdü."
                )

            return cleaned

        return self._fallback.synthesize(
            user_message=user_message,
            instruction=instruction,
            tool_call=tool_call,
            tool_result=tool_result,
        )