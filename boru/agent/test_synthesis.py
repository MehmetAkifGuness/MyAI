from boru.agent.models import AgentObservation


class GroundedTestRunSynthesizer:
    """Render a bounded targeted-test result directly from sandbox metadata."""

    _STATUSES = {"GEÇTİ", "BAŞARISIZ", "KANIT YETERSİZ"}

    def synthesize(self, observations: list[AgentObservation]) -> str | None:
        test_observations = tuple(
            item for item in observations if item.tool_name == "run_targeted_test"
        )
        if not test_observations:
            return None
        if len(test_observations) == 1:
            return self._single(test_observations[0])
        return self._batch(test_observations)

    def _single(self, observation: AgentObservation) -> str | None:
        if not observation.result.success:
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

    def _batch(self, observations: tuple[AgentObservation, ...]) -> str:
        results = [self._batch_result(item) for item in observations]
        lines = [
            f"{len(results)} test dosyası Docker sandbox içinde ayrı ayrı çalıştırıldı.",
            f"Genel durum: {self._overall_status(results)}",
            *(f"- `{path}`: {status} ({self._summary_values(summary)})" for path, status, summary, _ in results),
            "Toplam test özeti: " + self._summary_values(self._totals(results)),
        ]
        self._append_failure_evidence(lines, results)
        return "\n".join(lines)

    @staticmethod
    def _overall_status(results: list[tuple[str, str, dict[str, object], str]]) -> str:
        statuses = {status for _, status, _, _ in results}
        if "KANIT YETERSİZ" in statuses:
            return "KANIT YETERSİZ"
        if "BAŞARISIZ" in statuses:
            return "BAŞARISIZ"
        return "GEÇTİ"

    @staticmethod
    def _totals(
        results: list[tuple[str, str, dict[str, object], str]],
    ) -> dict[str, int]:
        totals = {key: 0 for key in ("total", "passed", "failed", "skipped")}
        for _, _, summary, _ in results:
            for key in totals:
                value = summary.get(key)
                if isinstance(value, int):
                    totals[key] += value
        return totals

    def _append_failure_evidence(
        self,
        lines: list[str],
        results: list[tuple[str, str, dict[str, object], str]],
    ) -> None:
        failures = tuple(
            (path, excerpt)
            for path, status, _, excerpt in results
            if status != "GEÇTİ" and excerpt
        )
        if not failures:
            return
        lines.extend(("", "Çalışma zamanı kanıtları:"))
        for path, excerpt in failures:
            lines.extend((f"`{path}`:", self._indent(excerpt[-1800:])))

    def _batch_result(
        self,
        observation: AgentObservation,
    ) -> tuple[str, str, dict[str, object], str]:
        if not observation.result.success:
            path = observation.arguments.get("path")
            return (
                path if isinstance(path, str) else "(bilinmeyen test)",
                "KANIT YETERSİZ",
                {},
                observation.result.error,
            )
        metadata = observation.result.metadata
        path = metadata.get("path")
        status = metadata.get("status")
        summary = metadata.get("summary")
        excerpt = metadata.get("output_excerpt")
        return (
            path if isinstance(path, str) else "(bilinmeyen test)",
            status if status in self._STATUSES else "KANIT YETERSİZ",
            summary if isinstance(summary, dict) else {},
            excerpt if isinstance(excerpt, str) else "",
        )

    @staticmethod
    def _summary_line(summary: dict[str, object]) -> str:
        return "Test özeti: " + GroundedTestRunSynthesizer._summary_values(summary)

    @staticmethod
    def _summary_values(summary: dict[str, object]) -> str:
        return (
            f"toplam={summary.get('total')}, geçti={summary.get('passed')}, "
            f"başarısız={summary.get('failed')}, atlandı={summary.get('skipped')}"
        )

    @staticmethod
    def _indent(text: str) -> str:
        return "\n".join(f"    {line}" for line in text.splitlines())
