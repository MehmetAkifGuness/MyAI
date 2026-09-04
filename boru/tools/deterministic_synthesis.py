import re

from boru.tools.models import (
    ToolCall,
    ToolResult,
)


class DirectoryCountSynthesisResolver:
    """Klasör öğe sayısını LLM'e saydırmadan metadata üzerinden yanıtlar."""

    _COUNT_PATTERNS = (
        re.compile(
            r"\bkaç\s+(?:tane\s+)?(?:öğe|öge|dosya|klasör|eleman)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bkaç\s+tane\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:öğe|öge|dosya|klasör|eleman)\s+say",
            re.IGNORECASE,
        ),
    )

    def resolve(
        self,
        *,
        user_message: str,
        instruction: str,
        tool_call: ToolCall,
        tool_result: ToolResult,
    ) -> str | None:
        del user_message

        if tool_call.tool_name != "list_directory":
            return None

        if not any(
            pattern.search(instruction)
            for pattern in self._COUNT_PATTERNS
        ):
            return None

        entry_count = tool_result.metadata.get(
            "entry_count"
        )
        display_path = tool_result.metadata.get(
            "display_path"
        )

        if (
            not isinstance(entry_count, int)
            or isinstance(entry_count, bool)
            or entry_count < 0
        ):
            return None

        if not isinstance(display_path, str):
            return None

        cleaned_path = display_path.strip()
        if not cleaned_path:
            return None

        if cleaned_path == "proje kökü":
            return (
                f"Proje kökünde {entry_count} öğe var."
            )

        return (
            f"{cleaned_path} klasöründe {entry_count} öğe var."
        )