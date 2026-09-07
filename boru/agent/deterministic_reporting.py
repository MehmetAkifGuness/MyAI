from boru.agent.impact_synthesis import GroundedImpactSynthesizer
from boru.agent.models import AgentAction, AgentActionKind, AgentObservation
from boru.agent.reporting import AgentReportRenderer
from boru.agent.test_synthesis import GroundedTestRunSynthesizer


class DeterministicEvidenceReportResolver:
    """Resolve structured runtime evidence before invoking a language model."""

    def __init__(self, reporter: AgentReportRenderer) -> None:
        self._reporter = reporter
        self._test_synthesizer = GroundedTestRunSynthesizer()
        self._impact_synthesizer = GroundedImpactSynthesizer()

    def render(
        self,
        objective: str,
        observations: list[AgentObservation],
    ) -> str | None:
        answer = self._test_synthesizer.synthesize(observations)
        if answer is None:
            answer = self._impact_synthesizer.synthesize(objective, observations)
        if answer is None:
            return None
        action = AgentAction(
            kind=AgentActionKind.FINAL,
            answer=answer,
            evidence=tuple(
                item.step for item in observations if item.result.success
            ),
        )
        return self._reporter.render_final(action, observations, objective)
