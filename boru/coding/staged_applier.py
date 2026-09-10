import hashlib
from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from boru.evaluation.models import Verdict
from boru.sandbox.snapshot import SourceSnapshot
from boru.tools.edit_workspace import SafeEditWorkspace
from boru.tools.project_transaction import BatchProjectEditApplier
from boru.tools.write_workspace import SafeWriteWorkspace
from boru.tools.workspace import ReadOnlyWorkspace


class StagedCodingApplier:
    """Validate an approved transaction in isolation before touching the project."""

    def __init__(self, root: Path, evaluator_factory, delegate):
        self._root = root.resolve()
        self._evaluator_factory = evaluator_factory
        self._delegate = delegate
        self.last_validation = None
        self.validation_paths = ()
        self.context_fingerprints = ()

    def apply_project_edit(self, proposal):
        self.last_validation = None
        reader = ReadOnlyWorkspace(self._root)
        for path, digest in self.context_fingerprints:
            if hashlib.sha256(reader.read_text_file(path).encode('utf-8')).hexdigest() != digest:
                raise ValueError('Araştırma/onay sonrasında kanıt dosyası değişti: ' + path)
        workspace = SafeEditWorkspace(self._root)
        for edit in proposal.edits:
            if workspace.read_edit_source(edit.path).sha256 != edit.expected_sha256:
                raise ValueError("Önizlemeden sonra kaynak değişmiş; öneri uygulanmadı.")
        changed_paths = tuple(dict.fromkeys(item.path for item in (*proposal.edits, *proposal.creations)))
        paths = tuple(dict.fromkeys((*changed_paths, *self.validation_paths)))
        baseline_evaluator = self._evaluator_factory(self._root)
        existing_paths = tuple(dict.fromkeys((*(edit.path for edit in proposal.edits), *self.validation_paths)))
        baseline_findings = Counter(
            baseline_evaluator.static_findings(existing_paths) if existing_paths else ()
        )
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
            evaluator = self._evaluator_factory(staged_root)
            report = evaluator.evaluate(paths)
            candidate_findings = Counter(evaluator.static_findings(paths))
            new_findings = candidate_findings - baseline_findings
            report = self._apply_static_delta(
                report,
                baseline_findings,
                candidate_findings,
                new_findings,
            )
            self.last_validation = report
            if report.verdict is not Verdict.PASS or new_findings or not evaluator.is_current(report):
                raise ValueError("Geçici kopya doğrulaması geçmedi; ana kaynaklar değiştirilmedi.\n" + report.render())
            if SourceSnapshot(self._root).read_sources() != baseline:
                raise ValueError("Doğrulama sırasında proje/test değişti; öneri uygulanmadı.")
            return self._delegate.apply_project_edit(proposal)

    @staticmethod
    def _apply_static_delta(report, baseline, candidate, new_findings):
        checks = []
        for check in report.checks:
            if check.name not in {"Security", "Code Review"}:
                checks.append(check)
                continue
            new_for_check = tuple(item for item in new_findings if item[0] == check.name)
            if new_for_check:
                checks.append(check)
                continue
            existing = sum(
                count for item, count in candidate.items() if item[0] == check.name
            )
            if existing and check.verdict is Verdict.FAIL:
                checks.append(replace(
                    check,
                    verdict=Verdict.PASS,
                    detail=(
                        f"Yeni bulgu yok; önceden var olan {existing} bulgu artırılmadı."
                    ),
                ))
            else:
                checks.append(check)
        return replace(report, checks=tuple(checks))
