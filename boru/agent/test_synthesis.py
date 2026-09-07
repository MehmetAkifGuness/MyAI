from boru.agent.models import AgentObservation


class GroundedTestRunSynthesizer:
    """Render a bounded targeted-test result directly from sandbox metadata."""

    _STATUSES = {"GEÇTİ", "BAŞARISIZ", "KANIT YETERSİZ"}

    def synthesize(self, observations: list[AgentObservation]) -> str | None:
        observation = next(
            (
                item
                for item in reversed(observations)
                if item.tool_name == "run_targeted_test" and item.result.success
            ),
            None,
        )
        if observation is None:
            return None
        metadata = observation.result.metadata
        path = metadata.get("path")
        runner = metadata.get("runner")
        status = metadata.get("status")
        summary = metadata.get("summary")
        if (
            not isinstance(path, str)
            or not isinstance(runner, str)
            or status not in self._STATUSES
            or not isinstance(summary, dict)
        ):
            return None
        lines = [
            f"`{path}` Docker sandbox içinde `{runner}` ile çalıştırıldı.",
            f"Durum: {status}",
            self._summary_line(summary),
        ]
        if status != "GEÇTİ":
            evidence = metadata.get("output_excerpt")
            if isinstance(evidence, str) and evidence.strip():
                lines.extend(("", "Çalışma zamanı kanıtı:", self._indent(evidence[-2500:])))
        return "\n".join(lines)

    @staticmethod
    def _summary_line(summary: dict[str, object]) -> str:
        return (
            "Test özeti: "
            f"toplam={summary.get('total')}, geçti={summary.get('passed')}, "
            f"başarısız={summary.get('failed')}, atlandı={summary.get('skipped')}"
        )

    @staticmethod
    def _indent(text: str) -> str:
        return "\n".join(f"    {line}" for line in text.splitlines())
