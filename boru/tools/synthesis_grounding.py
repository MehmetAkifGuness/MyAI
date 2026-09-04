import json
import re
from dataclasses import dataclass

from boru.tools.models import (
    ToolResult,
)


@dataclass(frozen=True, slots=True)
class RequiredEvidenceFact:
    source_line: str
    identifier: str
    value: str


@dataclass(frozen=True, slots=True)
class GroundedSynthesisPayload:
    answer: str
    evidence: tuple[str, ...]


class JsonGroundedSynthesisParser:
    """LLM çıktısından doğrulanabilir answer/evidence JSON nesnesi çıkarır."""

    def __init__(
        self,
        *,
        max_evidence_items: int = 12,
    ):
        if max_evidence_items < 1:
            raise ValueError(
                "max_evidence_items en az 1 olmalıdır."
            )

        self._max_evidence_items = (
            max_evidence_items
        )

    def parse(
        self,
        raw_output: str,
    ) -> GroundedSynthesisPayload:
        data = self._extract_json_object(
            raw_output
        )

        answer = data.get("answer")
        evidence = data.get("evidence")

        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(
                "Grounded synthesis çıktısında geçerli 'answer' yok."
            )

        if not isinstance(evidence, list):
            raise ValueError(
                "Grounded synthesis çıktısında 'evidence' liste olmalıdır."
            )

        if not evidence:
            raise ValueError(
                "Grounded synthesis en az bir kanıt içermelidir."
            )

        if len(evidence) > self._max_evidence_items:
            raise ValueError(
                "Grounded synthesis çok fazla kanıt içeriyor."
            )

        cleaned_evidence: list[str] = []

        for item in evidence:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    "Grounded synthesis kanıtları boş olmayan metinler olmalıdır."
                )

            cleaned = item.strip()
            if cleaned not in cleaned_evidence:
                cleaned_evidence.append(
                    cleaned
                )

        return GroundedSynthesisPayload(
            answer=answer.strip(),
            evidence=tuple(
                cleaned_evidence
            ),
        )

    @staticmethod
    def _extract_json_object(
        raw_output: str,
    ) -> dict[str, object]:
        text = raw_output.strip()
        if not text:
            raise ValueError(
                "Grounded synthesis modeli boş çıktı döndürdü."
            )

        decoder = json.JSONDecoder()

        for index, character in enumerate(text):
            if character != "{":
                continue

            try:
                candidate, _ = decoder.raw_decode(
                    text[index:]
                )
            except json.JSONDecodeError:
                continue

            if isinstance(candidate, dict):
                return candidate

        raise ValueError(
            "Grounded synthesis çıktısında geçerli JSON nesnesi bulunamadı."
        )


class AssignmentRequiredEvidenceExtractor:
    """Tüm/çoğul isteklerde ilgili sabit assignment satırlarını zorunlu kanıt yapar."""

    _ASSIGNMENT = re.compile(
        r"^\s*(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)"
        r"(?:\s*:\s*[^=]+)?\s*=\s*"
        r"(?P<value>"
        r"\"[^\"\n]*\"|"
        r"'[^'\n]*'|"
        r"[-+]?\d+(?:\.\d+)?|"
        r"True|False|None"
        r")\s*$"
    )

    _COMPLETENESS_PATTERNS = (
        re.compile(r"\btüm\b", re.IGNORECASE),
        re.compile(r"\bhepsi(?:ni|nin|si)?\b", re.IGNORECASE),
        re.compile(r"\btamam(?:ı|ını|ının)?\b", re.IGNORECASE),
        re.compile(
            r"\bhangi\s+\w*(?:ler|lar)\w*\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b\w*(?:modeller|ayarlar|değerler|degerler|parametreler)\w*\b",
            re.IGNORECASE,
        ),
    )

    def extract(
        self,
        *,
        instruction: str,
        tool_result: ToolResult,
    ) -> tuple[RequiredEvidenceFact, ...]:
        if tool_result.tool_name != "read_file":
            return ()

        if not self._requires_completeness(
            instruction
        ):
            return ()

        folded_instruction = (
            instruction.casefold()
        )
        facts: list[RequiredEvidenceFact] = []

        for raw_line in tool_result.content.splitlines():
            line = raw_line.strip()
            match = self._ASSIGNMENT.fullmatch(
                line
            )

            if match is None:
                continue

            identifier = match.group(
                "identifier"
            )

            if not self._identifier_matches_instruction(
                identifier,
                folded_instruction,
            ):
                continue

            raw_value = match.group("value")
            value = self._strip_literal_quotes(
                raw_value
            )

            facts.append(
                RequiredEvidenceFact(
                    source_line=line,
                    identifier=identifier,
                    value=value,
                )
            )

        return tuple(facts)

    def _requires_completeness(
        self,
        instruction: str,
    ) -> bool:
        return any(
            pattern.search(instruction)
            is not None
            for pattern in self._COMPLETENESS_PATTERNS
        )

    @staticmethod
    def _identifier_matches_instruction(
        identifier: str,
        folded_instruction: str,
    ) -> bool:
        segments = (
            segment.casefold()
            for segment in identifier.split("_")
        )

        return any(
            len(segment) >= 4
            and segment in folded_instruction
            for segment in segments
        )

    @staticmethod
    def _strip_literal_quotes(
        value: str,
    ) -> str:
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            return value[1:-1]

        return value


class GroundedSynthesisValidator:
    """LLM cevap ve kanıtlarının tool kaynağından geldiğini doğrular."""

    _TECHNICAL_TOKEN = re.compile(
        r"\b(?=[A-Za-z0-9_.:-]*[A-Za-z])"
        r"(?=[A-Za-z0-9_.:-]*\d)"
        r"[A-Za-z0-9][A-Za-z0-9_.:-]*\b"
    )

    def validate(
        self,
        *,
        payload: GroundedSynthesisPayload,
        tool_result: ToolResult,
        required_facts: tuple[RequiredEvidenceFact, ...] = (),
    ) -> None:
        source = self._normalize(
            tool_result.content
        )

        for evidence in payload.evidence:
            normalized_evidence = self._normalize(
                evidence
            )

            if normalized_evidence not in source:
                raise ValueError(
                    "LLM tarafından verilen kanıt tool sonucunda bulunmuyor."
                )

        for fact in required_facts:
            normalized_line = self._normalize(
                fact.source_line
            )

            if not any(
                normalized_line
                in self._normalize(evidence)
                for evidence in payload.evidence
            ):
                raise ValueError(
                    f"Zorunlu kanıt eksik: {fact.identifier}"
                )

            if fact.value.casefold() not in payload.answer.casefold():
                raise ValueError(
                    f"Zorunlu değer cevapta eksik: {fact.identifier}"
                )

        for token in self._TECHNICAL_TOKEN.findall(
            payload.answer
        ):
            if token.casefold() not in source.casefold():
                raise ValueError(
                    f"Cevaptaki teknik değer kaynakta bulunmuyor: {token}"
                )

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value.replace("\r\n", "\n")
            .replace("\r", "\n")
            .split()
        )