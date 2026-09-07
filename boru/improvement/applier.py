import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from boru.evaluation.models import Verdict
from boru.sandbox.snapshot import SourceSnapshot
from boru.tools.edit_models import EditProposal
from boru.tools.edit_workspace import SafeEditWorkspace
from boru.tools.project_edit_models import ProjectEditProposal
from boru.tools.project_transaction import BatchProjectEditApplier


class VerifiedImprovementApplier:
    """Validates proposed edits in a copy, commits atomically, keeps one guarded undo."""

    def __init__(self, root: Path, evaluator_factory):
        self._root = root.resolve()
        self._workspace = SafeEditWorkspace(root)
        self._delegate = BatchProjectEditApplier(workspace=self._workspace)
        self._evaluator_factory = evaluator_factory
        self.allowed_paths: tuple[str, ...] = ()
        self.last_validation = None
        self._undo: ProjectEditProposal | None = None

    @property
    def can_undo(self) -> bool:
        return self._undo is not None

    def validate_proposal(self, proposal: ProjectEditProposal) -> None:
        if proposal.creations:
            raise ValueError("İyileştirme yalnızca açıkça belirtilen mevcut dosyaları düzenleyebilir.")
        allowed = {path.replace("\\", "/").casefold() for path in self.allowed_paths}
        if not proposal.edits or any(edit.path.replace("\\", "/").casefold() not in allowed for edit in proposal.edits):
            raise ValueError("İyileştirme önerisi izin verilen kapsam dışında.")

    def apply_project_edit(self, proposal: ProjectEditProposal):
        self.last_validation = None
        self.validate_proposal(proposal)
        originals = {edit.path: self._workspace.read_edit_source(edit.path) for edit in proposal.edits}
        if any(originals[edit.path].sha256 != edit.expected_sha256 for edit in proposal.edits):
            raise ValueError("Önizlemeden sonra kaynak değişmiş; yeniden öneri hazırlayın.")
        with TemporaryDirectory(prefix="boru-improvement-") as directory:
            staged_root = Path(directory)
            baseline_sources = SourceSnapshot(self._root).copy_to(staged_root)
            staged_workspace = SafeEditWorkspace(staged_root)
            for edit in proposal.edits:
                current = staged_workspace.read_edit_source(edit.path)
                staged_workspace.apply_text_update(
                    relative_path=edit.path, content=edit.updated_content, expected_sha256=current.sha256)
            evaluator = self._evaluator_factory(staged_root)
            self.last_validation = evaluator.evaluate(self.allowed_paths)
            if self.last_validation.verdict is not Verdict.PASS:
                raise ValueError("Geçici kopya kontrolleri geçmedi; kaynaklar değiştirilmedi.\n"
                                 + self.last_validation.render())
        if SourceSnapshot(self._root).read_sources() != baseline_sources:
            raise ValueError("Doğrulama sırasında proje/test kaynakları değişti; öneri uygulanmadı.")
        # Recheck every original at the transaction boundary; preserve user edits.
        undo_edits = []
        for edit in proposal.edits:
            source = originals[edit.path]
            current_bytes = (self._root / edit.path).read_bytes()
            bom = b"\xef\xbb\xbf" if current_bytes.startswith(b"\xef\xbb\xbf") else b""
            committed_hash = hashlib.sha256(bom + edit.updated_content.encode("utf-8")).hexdigest()
            undo_edits.append(EditProposal(edit.path, source.content, committed_hash,
                                          "İyileştirme öncesi içeriğe geri dönüş",
                                          len(edit.updated_content), len(source.content)))
        outcome = self._delegate.apply_project_edit(proposal)
        self._undo = ProjectEditProposal("Son onaylı iyileştirmeyi geri al", tuple(undo_edits))
        return outcome

    def rollback(self):
        if self._undo is None:
            raise ValueError("Geri alınacak iyileştirme yok; kayıt yalnızca bu oturumda tutulur.")
        outcome = self._delegate.apply_project_edit(self._undo)
        self._undo = None
        return outcome
