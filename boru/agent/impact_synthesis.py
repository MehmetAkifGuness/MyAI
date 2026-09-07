from boru.agent.models import AgentObservation


class GroundedImpactSynthesizer:
    """Render impact-analysis metadata without another model generation."""

    _CUES = ("etkilen", "etki", "kim kullan", "nereden çağr")

    def synthesize(
        self,
        objective: str,
        observations: list[AgentObservation],
    ) -> str | None:
        if not any(cue in objective.casefold() for cue in self._CUES):
            return None
        observation = self._impact_observation(observations)
        if observation is None:
            return None
        payload = self._payload(observation)
        if payload is None:
            return None
        return self._render(*payload)

    @staticmethod
    def _impact_observation(
        observations: list[AgentObservation],
    ) -> AgentObservation | None:
        return next(
            (
                item
                for item in reversed(observations)
                if item.tool_name == "impact_analysis" and item.result.success
            ),
            None,
        )

    def _payload(
        self,
        observation: AgentObservation,
    ) -> tuple[str, tuple[dict[str, object], ...]] | None:
        source = observation.result.metadata.get("path")
        raw_impacts = observation.result.metadata.get("impacts")
        if not isinstance(source, str) or not isinstance(raw_impacts, (list, tuple)):
            return None
        impacts = tuple(
            item for item in raw_impacts if self._is_valid_impact(item)
        )
        return source, impacts

    @staticmethod
    def _render(source: str, impacts: tuple[dict[str, object], ...]) -> str:
        if not impacts:
            return (
                f"`{source}` için proje içi doğrudan veya dolaylı ters bağımlılık "
                "bulunamadı."
            )
        lines = [f"`{source}` değiştiğinde etkilenen proje içi dosyalar:"]
        for item in impacts:
            relation = "doğrudan" if item["distance"] == 1 else "dolaylı"
            kind = "test" if item["is_test"] else "çağıran"
            lines.append(
                f"- `{item['path']}` — {relation} {kind}; import zinciri: "
                f"`{item['imported_via']}`; mesafe: {item['distance']}"
            )
        tests = tuple(item["path"] for item in impacts if item["is_test"])
        lines.append("")
        lines.append(
            "Çalıştırılması gereken etkilenen testler: "
            + (", ".join(f"`{path}`" for path in tests) if tests else "bulunamadı")
        )
        return "\n".join(lines)

    @staticmethod
    def _is_valid_impact(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        return (
            isinstance(item.get("path"), str)
            and isinstance(item.get("distance"), int)
            and not isinstance(item.get("distance"), bool)
            and item.get("distance", 0) > 0
            and isinstance(item.get("imported_via"), str)
            and isinstance(item.get("is_test"), bool)
        )
