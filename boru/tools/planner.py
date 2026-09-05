import re

from boru.tools.models import (
    ToolCall,
    ToolDecision,
    ToolResponseMode,
)


class RuleBasedToolPlanner:
    """Açık ve düşük riskli tool niyetlerini deterministik seçer."""

    _TIME_PATTERNS = (
        re.compile(r"\bsaat\s+kaç\b", re.IGNORECASE),
        re.compile(r"\bşu\s+an(?:da)?\s+saat\b", re.IGNORECASE),
        re.compile(r"\bbugünün\s+tarihi\b", re.IGNORECASE),
        re.compile(r"\bbugün\s+tarih\b", re.IGNORECASE),
        re.compile(r"\btarih\s+ne\b", re.IGNORECASE),
    )

    _READ_FILE_PATTERNS = (
        re.compile(
            r"^\s*(?P<path>.+?)\s+dosyasını\s+"
            r"(?:oku|göster|aç)"
            r"(?P<instruction>.*?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<path>.+?)\s+dosyasının\s+içeriğini\s+"
            r"(?:oku|göster)"
            r"(?P<instruction>.*?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<path>.+?)\s+içeriğini\s+"
            r"(?:oku|göster)"
            r"(?P<instruction>.*?)\s*$",
            re.IGNORECASE,
        ),
    )

    _LIST_DIRECTORY_PATTERNS = (
        re.compile(
            r"^\s*projedeki\s+dosyaları\s+"
            r"(?:listele|göster)"
            r"(?P<instruction>.*?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<path>.+?)\s+klasöründeki\s+dosyaları\s+"
            r"(?:listele|göster)"
            r"(?P<instruction>.*?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<path>.+?)\s+klasörünü\s+"
            r"(?:listele|göster)"
            r"(?P<instruction>.*?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?:proje\s+)?(?:klasöründeki\s+)?dosyaları\s+"
            r"(?:listele|göster)"
            r"(?P<instruction>.*?)\s*$",
            re.IGNORECASE,
        ),
    )

    _WORD_OPERATORS = (
        (re.compile(r"\bartı\b", re.IGNORECASE), "+"),
        (re.compile(r"\beksi\b", re.IGNORECASE), "-"),
        (re.compile(r"\bçarpı\b", re.IGNORECASE), "*"),
        (re.compile(r"\bbölü\b", re.IGNORECASE), "/"),
    )

    _CALCULATE_PREFIX = re.compile(
        r"^\s*hesapla(?:r\s+mısın|r\s+mısınız)?\s*[:=]?\s*(.+?)\s*[?!.]*\s*$",
        re.IGNORECASE,
    )

    _QUESTION_SUFFIX = re.compile(
        r"\s*(?:kaç|kaçtır|nedir|ne\s+eder|sonucu\s+nedir)\s*[?!.]*\s*$",
        re.IGNORECASE,
    )

    _VALID_EXPRESSION = re.compile(
        r"^[0-9\s()+\-*/%.]+$"
    )

    _INSTRUCTION_PREFIX = re.compile(
        r"^[\s,;:-]*(?:(?:ve|sonra|ardından)\s+)?",
        re.IGNORECASE,
    )

    def plan(
        self,
        user_message: str,
    ) -> ToolDecision:
        text = " ".join(
            user_message.strip().split()
        )

        if not text:
            return ToolDecision.no_tool(
                "Boş mesaj."
            )

        if any(
            pattern.search(text)
            for pattern in self._TIME_PATTERNS
        ):
            return ToolDecision.use(
                ToolCall(
                    tool_name="get_current_time",
                ),
                reason="Açık tarih/saat isteği.",
            )

        file_match = self._match_tool_request(
            text,
            self._READ_FILE_PATTERNS,
        )

        if file_match is not None:
            file_path, instruction = file_match
            return self._build_tool_decision(
                tool_name="read_file",
                path=file_path,
                instruction=instruction,
                reason="Açık dosya okuma isteği.",
            )

        directory_match = self._match_tool_request(
            text,
            self._LIST_DIRECTORY_PATTERNS,
        )

        if directory_match is not None:
            directory_path, instruction = directory_match
            return self._build_tool_decision(
                tool_name="list_directory",
                path=directory_path,
                instruction=instruction,
                reason="Açık klasör listeleme isteği.",
            )

        expression = self._extract_expression(
            text
        )

        if expression is None:
            return ToolDecision.no_tool(
                "Desteklenen açık tool niyeti bulunamadı."
            )

        return ToolDecision.use(
            ToolCall(
                tool_name="calculator",
                arguments={
                    "expression": expression,
                },
            ),
            reason="Açık aritmetik hesaplama isteği.",
        )

    @classmethod
    def _match_tool_request(
        cls,
        text: str,
        patterns: tuple[re.Pattern[str], ...],
    ) -> tuple[str, str] | None:
        for pattern in patterns:
            match = pattern.fullmatch(text)
            if match is None:
                continue

            groups = match.groupdict()
            raw_path = groups.get("path")
            path = (
                "."
                if raw_path is None
                else cls._clean_path_phrase(raw_path)
            )

            instruction = cls._clean_instruction(
                groups.get("instruction") or ""
            )

            return path, instruction

        return None

    @classmethod
    def _build_tool_decision(
        cls,
        *,
        tool_name: str,
        path: str,
        instruction: str,
        reason: str,
    ) -> ToolDecision:
        call = ToolCall(
            tool_name=tool_name,
            arguments={
                "path": path,
            },
        )

        if not instruction:
            return ToolDecision.use(
                call,
                reason=reason,
            )

        return ToolDecision.use(
            call,
            reason=reason,
            response_mode=ToolResponseMode.SYNTHESIZE,
            synthesis_instruction=instruction,
        )

    @staticmethod
    def _clean_path_phrase(
        value: str,
    ) -> str:
        cleaned = value.strip()

        if (
            len(cleaned) >= 2
            and cleaned[0] == cleaned[-1]
            and cleaned[0] in {'"', "'"}
        ):
            cleaned = cleaned[1:-1].strip()

        if cleaned.casefold() in {
            "proje",
            "proje kökü",
            "proje klasörü",
        }:
            return "."

        return cleaned or "."

    @classmethod
    def _clean_instruction(
        cls,
        value: str,
    ) -> str:
        cleaned = value.strip()
        cleaned = cls._INSTRUCTION_PREFIX.sub(
            "",
            cleaned,
            count=1,
        )
        return cleaned.strip(" \t\r\n.,;:!?")

    def _extract_expression(
        self,
        text: str,
    ) -> str | None:
        candidate = text

        prefix_match = self._CALCULATE_PREFIX.fullmatch(
            text
        )

        if prefix_match is not None:
            candidate = prefix_match.group(1)
        else:
            stripped = self._QUESTION_SUFFIX.sub(
                "",
                text,
            )

            if stripped == text:
                return None

            candidate = stripped

        for pattern, replacement in self._WORD_OPERATORS:
            candidate = pattern.sub(
                replacement,
                candidate,
            )

        candidate = re.sub(
            r"(?<=\d),(?=\d)",
            ".",
            candidate,
        )
        candidate = candidate.strip()

        if not candidate:
            return None

        if not self._VALID_EXPRESSION.fullmatch(
            candidate
        ):
            return None

        if not any(
            character.isdigit()
            for character in candidate
        ):
            return None

        return candidate
