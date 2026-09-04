import re
from collections.abc import Sequence

from boru.tools.contracts import (
    ToolCandidateDetector,
    ToolPlanner,
)
from boru.tools.models import (
    ToolCall,
    ToolDecision,
    ToolResponseMode,
)


class NaturalLanguageToolPlanner:
    """Yaygın doğal dosya/klasör ifadelerini deterministik ToolCall'a çevirir."""

    _DIRECTORY_PATTERNS = (
        re.compile(
            r"^\s*(?P<path>[\w./\\-]+)\s+altında\s+neler\s+var\s*[?!.]*\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<path>[\w./\\-]+)\s+içinde\s+neler\s+var\s*[?!.]*\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(?P<path>[\w./\\-]+)\s+tarafında\s+neler\s+var\s*[?!.]*\s*$",
            re.IGNORECASE,
        ),
    )

    _FILE_LOOK_PATTERN = re.compile(
        r"^\s*(?P<path>[^,?!]+?)\s+tarafına\s+bir\s+bak"
        r"(?:ıp|ıp)?\s*[,;:-]?\s*(?P<instruction>.+?)\s*[?!.]*\s*$",
        re.IGNORECASE,
    )

    _FILE_LOOK_SHORT_PATTERN = re.compile(
        r"^\s*(?P<path>[^,?!]+?)\s+tarafına\s+bak(?:ıp)?"
        r"\s*[,;:-]?\s*(?P<instruction>.+?)\s*[?!.]*\s*$",
        re.IGNORECASE,
    )

    _KNOWN_FILE_SUFFIXES = (
        ".py",
        ".json",
        ".txt",
        ".md",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".env",
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

        directory_path = self._match_directory(
            text
        )
        if directory_path is not None:
            return ToolDecision.use(
                ToolCall(
                    tool_name="list_directory",
                    arguments={
                        "path": directory_path,
                    },
                ),
                reason="Doğal klasör listeleme isteği.",
            )

        file_request = self._match_file_look(
            text
        )
        if file_request is not None:
            path, instruction = file_request
            return ToolDecision.use(
                ToolCall(
                    tool_name="read_file",
                    arguments={
                        "path": path,
                    },
                ),
                reason="Doğal dosya inceleme isteği.",
                response_mode=ToolResponseMode.SYNTHESIZE,
                synthesis_instruction=instruction,
            )

        return ToolDecision.no_tool(
            "Doğal tool kalıbı eşleşmedi."
        )

    @classmethod
    def _match_directory(
        cls,
        text: str,
    ) -> str | None:
        for pattern in cls._DIRECTORY_PATTERNS:
            match = pattern.fullmatch(text)
            if match is None:
                continue

            return cls._clean_path(
                match.group("path")
            )

        return None

    @classmethod
    def _match_file_look(
        cls,
        text: str,
    ) -> tuple[str, str] | None:
        for pattern in (
            cls._FILE_LOOK_PATTERN,
            cls._FILE_LOOK_SHORT_PATTERN,
        ):
            match = pattern.fullmatch(text)
            if match is None:
                continue

            path = cls._clean_path(
                match.group("path")
            )
            instruction = cls._clean_instruction(
                match.group("instruction")
            )

            if not cls._looks_like_file(path):
                continue

            if not instruction:
                continue

            return path, instruction

        return None

    @classmethod
    def _looks_like_file(
        cls,
        path: str,
    ) -> bool:
        folded = path.casefold()
        return any(
            folded.endswith(suffix)
            for suffix in cls._KNOWN_FILE_SUFFIXES
        )

    @staticmethod
    def _clean_path(
        value: str,
    ) -> str:
        cleaned = value.strip().strip('"\'')

        if cleaned.casefold() in {
            "proje",
            "proje kökü",
            "proje klasörü",
        }:
            return "."

        return cleaned or "."

    @staticmethod
    def _clean_instruction(
        value: str,
    ) -> str:
        cleaned = value.strip(" \t\r\n,;:.!?")
        cleaned = re.sub(
            r"^(?:ve\s+)?",
            "",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )
        return cleaned.strip(" \t\r\n,;:.!?")


class ChainedToolPlanner:
    """Birden fazla deterministik planner'ı sırayla dener."""

    def __init__(
        self,
        planners: Sequence[ToolPlanner],
    ):
        self._planners = tuple(planners)

        if not self._planners:
            raise ValueError(
                "ChainedToolPlanner en az bir planner gerektirir."
            )

    def plan(
        self,
        user_message: str,
    ) -> ToolDecision:
        for planner in self._planners:
            decision = planner.plan(
                user_message
            )

            if decision.planning_failed:
                return decision

            if decision.should_use_tool:
                return decision

        return ToolDecision.no_tool(
            "Deterministik planner'lar tool seçmedi."
        )


class RuleBasedToolCandidateDetector:
    """Deterministik planner'lar çözemediğinde LLM planner'a gitmeye değer mesajları seçer."""

    _PATTERNS = (
        re.compile(
            r"\b(?:dosya|dosyalar|klasör|dizin|directory|folder)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:config|ayar|settings|tests?|testler)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:proje|project)\b.*\b(?:bak|incele|göster|listele|oku|kontrol)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:bak|incele|göster|listele|oku|kontrol)\b.*\b(?:proje|project)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|\s)[\w./\\-]+\.(?:py|json|txt|md|yaml|yml|toml|ini|cfg|env)(?:\s|$)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:altında|içinde|içeriğinde|içeriğine|içeriği|tarafına)\b.*\b(?:ne|neler|hangi|kaç|özet|bak)\b",
            re.IGNORECASE,
        ),
    )

    def is_candidate(
        self,
        user_message: str,
    ) -> bool:
        text = " ".join(
            user_message.strip().split()
        )

        if not text:
            return False

        return any(
            pattern.search(text)
            is not None
            for pattern in self._PATTERNS
        )


class FallbackToolPlanner:
    """Önce deterministik planner'ı, gerekirse kontrollü LLM fallback'i kullanır."""

    def __init__(
        self,
        *,
        primary: ToolPlanner,
        fallback: ToolPlanner,
        candidate_detector: ToolCandidateDetector | None = None,
    ):
        self._primary = primary
        self._fallback = fallback
        self._candidate_detector = (
            candidate_detector
            or RuleBasedToolCandidateDetector()
        )

    def plan(
        self,
        user_message: str,
    ) -> ToolDecision:
        primary_decision = self._primary.plan(
            user_message
        )

        if primary_decision.planning_failed:
            return primary_decision

        if primary_decision.should_use_tool:
            return primary_decision

        if not self._candidate_detector.is_candidate(
            user_message
        ):
            return primary_decision

        fallback_decision = self._fallback.plan(
            user_message
        )

        if fallback_decision.should_use_tool:
            return fallback_decision

        if fallback_decision.planning_failed:
            return fallback_decision

        return ToolDecision.planning_failure(
            "Tool adayı mesaj için güvenilir tool planı üretilemedi."
        )