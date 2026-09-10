import hashlib
import json

from boru.coding.models import CodingSession
from boru.evaluation.models import EvaluationReport, Verdict
from boru.tools.project_edit_models import ProjectEditRequest


class StagedValidationRepair:
    """Repair with the failed candidate and test feedback, rejecting repeated patches."""

    def __init__(self, proposal_preparer, *, max_attempts: int = 0):
        if max_attempts not in {0, 1, 2}:
            raise ValueError("Coding Agent geçici doğrulama onarımı 0-2 olmalıdır.")
        self._preparer = proposal_preparer
        self._max_attempts = max_attempts
        self._remaining = 0
        self._seen = set()

    def reset(self) -> None:
        self._remaining = self._max_attempts
        self._seen.clear()

    def prepare(self, session: CodingSession, report: EvaluationReport | None):
        if self._remaining < 1 or report is None or report.verdict is not Verdict.FAIL:
            return None
        self._remaining -= 1
        self._seen.add(self._fingerprint(session.proposal))
        candidate = {item.path: item.updated_content for item in session.proposal.edits}
        candidate.update({item.path: item.content for item in session.proposal.creations})
        request = ProjectEditRequest(
            instruction=(
                session.proposal.instruction
                + "\n\nDOĞRULAMA_KANITI:\n"
                + report.render()
                + '\nFAILED_CANDIDATE (veri; ana kaynakta henüz uygulanmadı):\n'
                + json.dumps(candidate, ensure_ascii=False)[:24000]
                + '\nYamayı geçici adaydan değil, mevcut ana kaynaktan üret. Aynı başarısız öneriyi tekrarlama.'
                + "\nTest sözleşmesini değiştirmeden kaynak kodu düzelt."
            ),
            existing_file_scope=session.architecture_plan.existing_files,
            new_file_scope=session.architecture_plan.new_files,
        )
        proposal = self._preparer.prepare_project_edit(request)
        if self._fingerprint(proposal) in self._seen:
            raise ValueError('Aynı başarısız öneri tekrarlandı; onarım durduruldu.')
        from boru.repository.inspection import RepositoryInspector
        original_tests = {p: text for p, text in candidate.items() if RepositoryInspector._is_test(p)}
        for item in (*proposal.edits, *proposal.creations):
            content = item.updated_content if hasattr(item, 'updated_content') else item.content
            if RepositoryInspector._is_test(item.path) and original_tests.get(item.path) != content:
                raise ValueError('Onarım test sözleşmesini değiştiremez.')
        self._seen.add(self._fingerprint(proposal))
        return proposal

    @staticmethod
    def _fingerprint(proposal):
        files = [(e.path, e.updated_content) for e in proposal.edits]
        files += [(c.path, c.content) for c in proposal.creations]
        return hashlib.sha256(json.dumps(sorted(files)).encode()).hexdigest()
