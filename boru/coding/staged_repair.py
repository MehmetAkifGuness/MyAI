from boru.coding.models import CodingSession
from boru.evaluation.models import EvaluationReport, Verdict
from boru.tools.project_edit_models import ProjectEditRequest


class StagedValidationRepair:
    """Creates at most one new proposal from a failed staged evaluation."""

    def __init__(self, proposal_preparer, *, max_attempts: int = 0):
        if max_attempts not in {0, 1}:
            raise ValueError("Coding Agent geçici doğrulama onarımı 0 veya 1 olmalıdır.")
        self._preparer = proposal_preparer
        self._max_attempts = max_attempts
        self._remaining = 0

    def reset(self) -> None:
        self._remaining = self._max_attempts

    def prepare(self, session: CodingSession, report: EvaluationReport | None):
        if self._remaining < 1 or report is None or report.verdict is not Verdict.FAIL:
            return None
        self._remaining -= 1
        request = ProjectEditRequest(
            instruction=(
                session.proposal.instruction
                + "\n\nDOĞRULAMA_KANITI:\n"
                + report.render()
                + "\nTest sözleşmesini değiştirmeden kaynak kodu düzelt."
            ),
            existing_file_scope=session.architecture_plan.existing_files,
            new_file_scope=session.architecture_plan.new_files,
        )
        return self._preparer.prepare_project_edit(request)
