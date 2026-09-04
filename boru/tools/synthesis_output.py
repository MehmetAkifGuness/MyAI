import re


class InternalLabelSynthesisOutputSanitizer:
    """LLM sentez çıktısından iç orchestration etiketlerini temizler."""

    _SYNTHESIS_SECTION = re.compile(
        r"(?is).*?\bSYNTHESIS_INSTRUCTION\b"
        r"(?:['’]?[a-zçğıöşü]*\s+göre\s+cevap)?"
        r"\s*:?\s*(?P<content>.+)$"
    )

    _INTERNAL_LABEL_LINE = re.compile(
        r"(?im)^\s*(?:"
        r"ORIGINAL_REQUEST|"
        r"SYNTHESIS_INSTRUCTION|"
        r"TOOL_NAME|"
        r"TOOL_ARGUMENTS|"
        r"TOOL_RESULT_TRUNCATED|"
        r"TOOL_RESULT_BEGIN|"
        r"TOOL_RESULT_END"
        r")"
        r"(?:['’]?[a-zçğıöşü]*\s+göre\s+cevap)?"
        r"\s*:?\s*$"
    )

    _INLINE_INTERNAL_LABEL = re.compile(
        r"(?i)\b(?:"
        r"ORIGINAL_REQUEST|"
        r"SYNTHESIS_INSTRUCTION|"
        r"TOOL_NAME|"
        r"TOOL_ARGUMENTS|"
        r"TOOL_RESULT_TRUNCATED|"
        r"TOOL_RESULT_BEGIN|"
        r"TOOL_RESULT_END"
        r")\b"
        r"(?:['’]?[a-zçğıöşü]*\s+göre\s+cevap)?"
        r"\s*:?"
    )

    _LEADING_ANSWER_LABEL = re.compile(
        r"(?i)^\s*(?:nihai\s+)?cevap\s*:\s*"
    )

    _MULTIPLE_BLANK_LINES = re.compile(
        r"\n{3,}"
    )

    def sanitize(
        self,
        answer: str,
    ) -> str:
        cleaned = answer.strip()
        if not cleaned:
            return ""

        synthesis_match = self._SYNTHESIS_SECTION.fullmatch(
            cleaned
        )
        if synthesis_match is not None:
            cleaned = synthesis_match.group(
                "content"
            ).strip()

        cleaned = self._INTERNAL_LABEL_LINE.sub(
            "",
            cleaned,
        )
        cleaned = self._INLINE_INTERNAL_LABEL.sub(
            "",
            cleaned,
        )
        cleaned = self._LEADING_ANSWER_LABEL.sub(
            "",
            cleaned,
            count=1,
        )
        cleaned = self._MULTIPLE_BLANK_LINES.sub(
            "\n\n",
            cleaned,
        )

        return cleaned.strip()

    def contains_internal_labels(
        self,
        answer: str,
    ) -> bool:
        return (
            self._INLINE_INTERNAL_LABEL.search(answer)
            is not None
        )