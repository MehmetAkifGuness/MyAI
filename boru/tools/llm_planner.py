import json
from collections.abc import Sequence
from dataclasses import dataclass

from boru.contracts import ChatModel
from boru.models import ChatMessage
from boru.tools.arguments import ToolArgumentSpec
from boru.tools.contracts import (
    ToolRegistryPort,
)
from boru.tools.models import (
    ToolCall,
    ToolDecision,
    ToolResponseMode,
)


@dataclass(frozen=True, slots=True)
class LLMToolPlanningPayload:
    should_use_tool: bool
    tool_name: str | None = None
    arguments: dict[str, object] | None = None
    response_mode: str = "direct"
    synthesis_instruction: str = ""
    reason: str = ""


class JsonLLMToolPlanningParser:
    """LLM planner çıktısından tek bir JSON planı güvenli biçimde çıkarır."""

    _ALLOWED_SCALAR_TYPES = (
        str,
        int,
        float,
        bool,
        type(None),
    )

    def parse(
        self,
        raw_output: str,
    ) -> LLMToolPlanningPayload:
        data = self._extract_json_object(
            raw_output
        )

        should_use_tool = data.get(
            "should_use_tool"
        )

        if not isinstance(
            should_use_tool,
            bool,
        ):
            raise ValueError(
                "LLM tool planında should_use_tool boolean olmalıdır."
            )

        tool_name = data.get("tool_name")
        arguments = data.get(
            "arguments",
            {},
        )
        response_mode = data.get(
            "response_mode",
            "direct",
        )
        synthesis_instruction = data.get(
            "synthesis_instruction",
            "",
        )
        reason = data.get(
            "reason",
            "",
        )

        if tool_name is not None and not isinstance(
            tool_name,
            str,
        ):
            raise ValueError(
                "LLM tool planında tool_name metin veya null olmalıdır."
            )

        if not isinstance(arguments, dict):
            raise ValueError(
                "LLM tool planında arguments JSON nesnesi olmalıdır."
            )

        if not all(
            isinstance(value, self._ALLOWED_SCALAR_TYPES)
            for value in arguments.values()
        ):
            raise ValueError(
                "LLM tool planı iç içe veya karmaşık argüman içeremez."
            )

        if not isinstance(response_mode, str):
            raise ValueError(
                "LLM tool planında response_mode metin olmalıdır."
            )

        if not isinstance(
            synthesis_instruction,
            str,
        ):
            raise ValueError(
                "LLM tool planında synthesis_instruction metin olmalıdır."
            )

        if not isinstance(reason, str):
            raise ValueError(
                "LLM tool planında reason metin olmalıdır."
            )

        return LLMToolPlanningPayload(
            should_use_tool=should_use_tool,
            tool_name=(
                tool_name.strip()
                if isinstance(tool_name, str)
                else None
            ),
            arguments=dict(arguments),
            response_mode=response_mode.strip(),
            synthesis_instruction=(
                synthesis_instruction.strip()
            ),
            reason=reason.strip(),
        )

    @staticmethod
    def _extract_json_object(
        raw_output: str,
    ) -> dict[str, object]:
        text = raw_output.strip()
        if not text:
            raise ValueError(
                "LLM tool planner boş çıktı döndürdü."
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
            "LLM tool planner çıktısında geçerli JSON nesnesi bulunamadı."
        )


class LLMToolPlanner:
    """Yalnızca registry'deki tool'lara izin veren fail-closed LLM planner."""

    _SYSTEM_PROMPT = (
        "Sen Börü'nün tek-tool planlama katmanısın. "
        "Kullanıcıya cevap verme; yalnızca tool gerekip gerekmediğine karar ver. "
        "SADECE aşağıdaki katalogda bulunan tool'lardan en fazla BİR tanesini seç. "
        "Katalogda olmayan write, delete, terminal, network veya başka bir aracı "
        "ASLA uydurma. Hedef dosya/klasör yolu yeterince açık değilse tool seçme. "
        "Kullanıcı yalnızca ham sonucu görmek istiyorsa response_mode='direct'; "
        "tool sonucunu yorumlama, özetleme, bilgi çıkarma veya sayma gibi ek bir "
        "isteği varsa response_mode='synthesize' ve synthesis_instruction alanına "
        "yalnızca bu ek görevi yaz. JSON dışında hiçbir şey üretme."
    )

    def __init__(
        self,
        chat_model: ChatModel,
        registry: ToolRegistryPort,
        parser: JsonLLMToolPlanningParser | None = None,
    ):
        self._chat_model = chat_model
        self._registry = registry
        self._parser = (
            parser
            or JsonLLMToolPlanningParser()
        )

    def plan(
        self,
        user_message: str,
    ) -> ToolDecision:
        try:
            payload = self._parser.parse(
                self._chat_model.generate(
                    [
                        ChatMessage(
                            role="system",
                            content=self._SYSTEM_PROMPT,
                        ),
                        ChatMessage(
                            role="user",
                            content=self._build_prompt(
                                user_message
                            ),
                        ),
                    ]
                )
            )

            return self._to_decision(
                payload
            )
        except Exception:
            return ToolDecision.planning_failure(
                "LLM tool planı doğrulanamadı; fail-closed."
            )

    def _to_decision(
        self,
        payload: LLMToolPlanningPayload,
    ) -> ToolDecision:
        if not payload.should_use_tool:
            if payload.tool_name:
                raise ValueError(
                    "Tool gerekmeyen plan tool_name içeremez."
                )

            if payload.arguments:
                raise ValueError(
                    "Tool gerekmeyen plan arguments içeremez."
                )

            if payload.response_mode.casefold() != "direct":
                raise ValueError(
                    "Tool gerekmeyen plan direct olmalıdır."
                )

            if payload.synthesis_instruction:
                raise ValueError(
                    "Tool gerekmeyen plan synthesis_instruction içeremez."
                )

            return ToolDecision.no_tool(
                payload.reason
                or "LLM planner tool gerekmiyor dedi."
            )

        tool_name = (
            payload.tool_name or ""
        ).strip()

        if not tool_name:
            raise ValueError(
                "Tool kullanılacaksa tool_name gereklidir."
            )

        if self._registry.get(tool_name) is None:
            raise ValueError(
                "LLM planner katalog dışı tool seçti."
            )

        try:
            response_mode = ToolResponseMode(
                payload.response_mode.casefold()
            )
        except ValueError as error:
            raise ValueError(
                "Geçersiz response_mode."
            ) from error

        instruction = (
            payload.synthesis_instruction.strip()
        )

        return ToolDecision.use(
            ToolCall(
                tool_name=tool_name,
                arguments=(
                    payload.arguments
                    or {}
                ),
            ),
            reason=(
                payload.reason
                or "LLM fallback planner tool seçti."
            ),
            response_mode=response_mode,
            synthesis_instruction=instruction,
        )

    @staticmethod
    def _format_arguments(
        arguments: Sequence[ToolArgumentSpec],
    ) -> str:
        if not arguments:
            return "none"

        rendered = []
        for argument in arguments:
            requirement = (
                "required"
                if argument.required
                else "optional"
            )

            rendered.append(
                f"{argument.name}:{argument.value_type.value}({requirement})"
            )

        return ",".join(rendered)

    def _build_prompt(
        self,
        user_message: str,
    ) -> str:
        definitions = self._registry.definitions()

        catalog_lines = [
            (
                f"- {definition.name} | risk={definition.risk.value} | "
                f"args={self._format_arguments(definition.arguments)} | "
                f"{definition.description}"
            )
            for definition in definitions
        ]

        catalog = (
            "\n".join(catalog_lines)
            if catalog_lines
            else "- katalog boş"
        )

        return (
            "AVAILABLE_TOOLS:\n"
            f"{catalog}\n\n"
            "USER_MESSAGE:\n"
            f"{user_message.strip()}\n\n"
            "Beklenen JSON şeması:\n"
            "{\n"
            '  "should_use_tool": true veya false,\n'
            '  "tool_name": "katalogdaki_ad" veya null,\n'
            '  "arguments": {},\n'
            '  "response_mode": "direct" veya "synthesize",\n'
            '  "synthesis_instruction": "",\n'
            '  "reason": "kısa gerekçe"\n'
            "}\n"
            "Tool gerekmiyorsa tool_name=null, arguments={}, "
            "response_mode='direct' ve synthesis_instruction='' kullan."
        )