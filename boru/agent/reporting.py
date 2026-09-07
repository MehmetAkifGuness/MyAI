import re

from boru.agent.models import AgentAction, AgentObservation
from boru.tools.models import ToolResult


class AgentReportRenderer:
    def usable_observations(
        self,
        observations: list[AgentObservation],
    ) -> list[AgentObservation]:
        return [item for item in observations if self._is_usable_evidence(item.result)]

    def render_final(
        self,
        action: AgentAction,
        observations: list[AgentObservation],
        objective: str,
    ) -> str | None:
        successful = {item.step: item for item in self.usable_observations(observations)}
        if not successful or not self._is_substantive_answer(action.answer, objective):
            return None
        evidence_lines = [
            f"- [T{number}] {self._evidence_label(observation)}"
            for number, observation in successful.items()
        ]
        return "\n".join(
            ["AJAN RAPORU", "Durum: TAMAMLANDI", "", action.answer, "", "Kanıtlar:", *evidence_lines]
        )

    @staticmethod
    def render_incomplete(
        observations: list[AgentObservation],
        validation_errors: list[str],
    ) -> str:
        lines = [
            "AJAN RAPORU",
            "Durum: TAMAMLANAMADI",
            "Ajan güvenli adım sınırı içinde kanıtlı bir sonuca ulaşamadı.",
        ]
        successful = [item for item in observations if item.result.success]
        if successful:
            lines.append("Başarılı gözlemler: " + ", ".join(f"T{item.step}" for item in successful))
        if validation_errors:
            lines.append("Son doğrulama: " + validation_errors[-1])
        failures = [item for item in observations if not item.result.success]
        for item in failures[-3:]:
            lines.append(f"T{item.step} {item.tool_name} hatası: {item.result.error}")
        return "\n".join(lines)

    @staticmethod
    def _is_substantive_answer(answer: str, objective: str) -> bool:
        cleaned = answer.strip()
        if re.fullmatch(r"[\w./\\-]+\.[A-Za-z0-9]+", cleaned):
            return False
        compound_markers = (" ve ", " nasıl ", "adım", "açıkla", "neden")
        compound = any(marker in objective.casefold() for marker in compound_markers)
        return len(cleaned) >= (100 if compound else 20)

    @staticmethod
    def _is_usable_evidence(result: ToolResult) -> bool:
        if not result.success:
            return False
        result_count = result.metadata.get("result_count")
        if isinstance(result_count, int) and result_count < 1:
            return False
        return bool(result.content.strip())

    @staticmethod
    def _evidence_label(observation: AgentObservation) -> str:
        label = observation.tool_name
        path = observation.result.metadata.get("path")
        if isinstance(path, str) and path:
            return f"{label} — {path}"
        paths = observation.result.metadata.get("paths")
        if not isinstance(paths, (list, tuple)):
            return label
        safe_paths = [item for item in paths if isinstance(item, str)][:5]
        return f"{label} — {', '.join(safe_paths)}" if safe_paths else label

