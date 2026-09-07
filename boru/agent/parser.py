import json

from boru.agent.models import AgentAction, AgentActionKind


class JsonAgentActionParser:
    _FIELDS = {"action", "tool_name", "arguments", "answer", "evidence", "reason"}
    _SCALAR_TYPES = (str, int, float, bool, type(None))

    def parse(self, raw_output: str) -> AgentAction:
        data = self._extract_object(raw_output)
        self._validate_fields(data)
        kind = self._parse_kind(data["action"])
        tool_name, answer, reason = self._parse_text_fields(data)
        arguments = self._parse_arguments(data["arguments"])
        evidence = self._parse_evidence(data["evidence"])
        if kind is AgentActionKind.TOOL:
            answer = ""
            evidence = ()
        else:
            tool_name = ""
            arguments = {}
        return AgentAction(
            kind=kind,
            tool_name=tool_name,
            arguments=arguments,
            answer=answer,
            evidence=evidence,
            reason=reason,
        )

    def _validate_fields(self, data: dict[str, object]) -> None:
        unexpected = set(data) - self._FIELDS
        if unexpected:
            raise ValueError("Ajan eylemi beklenmeyen alan içeriyor.")
        missing = self._FIELDS - set(data)
        if missing:
            raise ValueError("Ajan eylemi zorunlu alan içermiyor.")

    @staticmethod
    def _parse_kind(value: object) -> AgentActionKind:
        try:
            return AgentActionKind(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Ajan action alanı tool veya final olmalıdır.") from error

    @staticmethod
    def _parse_text_fields(data: dict[str, object]) -> tuple[str, str, str]:
        tool_name, answer, reason = data["tool_name"], data["answer"], data["reason"]
        if not isinstance(tool_name, str) or not isinstance(answer, str) or not isinstance(reason, str):
            raise ValueError("Ajan metin alanları geçersiz.")
        return tool_name, answer, reason

    def _parse_arguments(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item_value, self._SCALAR_TYPES)
            for key, item_value in value.items()
        ):
            raise ValueError("Ajan tool argümanları düz bir JSON nesnesi olmalıdır.")
        return dict(value)

    @staticmethod
    def _parse_evidence(value: object) -> tuple[int, ...]:
        if not isinstance(value, list) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in value
        ):
            raise ValueError("Ajan evidence alanı pozitif tam sayı listesi olmalıdır.")
        return tuple(dict.fromkeys(value))

    @staticmethod
    def _extract_object(raw_output: str) -> dict[str, object]:
        text = raw_output.strip()
        if not text:
            raise ValueError("Ajan modeli boş çıktı döndürdü.")
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                return candidate
        raise ValueError("Ajan çıktısında geçerli JSON nesnesi bulunamadı.")
