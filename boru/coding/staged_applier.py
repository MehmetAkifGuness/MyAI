from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from boru.evaluation.models import Verdict
from boru.sandbox.snapshot import SourceSnapshot
from boru.tools.edit_workspace import SafeEditWorkspace
from boru.tools.project_transaction import BatchProjectEditApplier
from boru.tools.write_workspace import SafeWriteWorkspace


class StagedCodingApplier:
    """Validate an approved transaction in isolation before touching the project."""

    def __init__(self, root: Path, evaluator_factory, delegate):
        self._root = root.resolve()
        self._evaluator_factory = evaluator_factory
        self._delegate = delegate
        self.last_validation = None

    def apply_project_edit(self, proposal):
        self.last_validation = None
        workspace = SafeEditWorkspace(self._root)
        for edit in proposal.edits:
            if workspace.read_edit_source(edit.path).sha256 != edit.expected_sha256:
                raise ValueError("Önizlemeden sonra kaynak değişmiş; öneri uygulanmadı.")
        with TemporaryDirectory(prefix="boru-coding-") as directory:
            staged_root = Path(directory)
            baseline = SourceSnapshot(self._root).copy_to(staged_root)
            staged_workspace = SafeEditWorkspace(staged_root)
            # Snapshot text normalization may change BOM/newline hashes.
            staged_proposal = replace(proposal, edits=tuple(
                replace(edit, expected_sha256=staged_workspace.read_edit_source(edit.path).sha256)
                for edit in proposal.edits
            ))
            BatchProjectEditApplier(workspace=staged_workspace,
                                    creation_workspace=SafeWriteWorkspace(staged_root)).apply_project_edit(staged_proposal)
            paths = tuple(dict.fromkeys(item.path for item in (*proposal.edits, *proposal.creations)))
            evaluator = self._evaluator_factory(staged_root)
            report = evaluator.evaluate(paths)
            self.last_validation = report
            if report.verdict is not Verdict.PASS or not evaluator.is_current(report):
                raise ValueError("Geçici kopya doğrulaması geçmedi; ana kaynaklar değiştirilmedi.\n" + report.render())
            if SourceSnapshot(self._root).read_sources() != baseline:
                raise ValueError("Doğrulama sırasında proje/test değişti; öneri uygulanmadı.")
            return self._delegate.apply_project_edit(proposal)
