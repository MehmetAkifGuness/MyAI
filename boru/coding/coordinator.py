from threading import RLock

from boru.architecture.contracts import ArchitecturePlanner
from boru.architecture.models import ArchitecturePlan
from boru.coding.models import CodingRequest, CodingSession
from boru.coding.parser import RuleBasedCodingRequestParser
from boru.reviewing.contracts import CodeReviewer
from boru.security.contracts import SecurityReviewer
from boru.testing.contracts import RegressionTestRunner
from boru.tools.deterministic_edit import SmartEditNotApplicable
from boru.tools.edit_contracts import SmartEditProposalPreparer, SmartEditRequestParser
from boru.tools.edit_models import SmartEditRequest
from boru.tools.project_edit_contracts import ProjectEditApplier, ProjectEditProposalPreparer
from boru.tools.project_edit_models import ProjectEditProposal, ProjectEditRequest


class ControlledCodingCoordinator:
    """Architect planını kapsam-korumalı diff ve açık onay akışına dönüştürür."""

    _APPROVE = "kod değişikliğini onayla"
    _CANCEL_COMMANDS = {"iptal", "vazgeç", "kod değişikliğini iptal et"}
    _USAGE = "Coding Agent biçimi: 'kodla: yapılacak değişiklik'."

    def __init__(
        self,
        *,
        parser: RuleBasedCodingRequestParser,
        architect: ArchitecturePlanner,
        proposal_preparer: ProjectEditProposalPreparer,
        proposal_applier: ProjectEditApplier,
        deterministic_edit_parser: SmartEditRequestParser | None = None,
        deterministic_edit_preparer: SmartEditProposalPreparer | None = None,
        regression_runner: RegressionTestRunner | None = None,
        security_reviewer: SecurityReviewer | None = None,
        code_reviewer: CodeReviewer | None = None,
        preview_characters: int = 8000,
    ) -> None:
        if preview_characters < 1:
            raise ValueError("Coding Agent önizleme sınırı pozitif olmalıdır.")
        if (deterministic_edit_parser is None) != (deterministic_edit_preparer is None):
            raise ValueError(
                "Coding Agent deterministik parser ve preparer birlikte verilmelidir."
            )
        self._parser = parser
        self._architect = architect
        self._proposal_preparer = proposal_preparer
        self._proposal_applier = proposal_applier
        self._deterministic_edit_parser = deterministic_edit_parser
        self._deterministic_edit_preparer = deterministic_edit_preparer
        self._regression_runner = regression_runner
        self._security_reviewer = security_reviewer
        self._code_reviewer = code_reviewer
        self._preview_characters = preview_characters
        self._pending: CodingSession | None = None
        self._lock = RLock()

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return self._pending is not None

    def resolve(self, user_message: str) -> str | None:
        normalized = " ".join(user_message.casefold().strip().split()).rstrip(".!?")
        with self._lock:
            if self._pending is not None:
                if normalized == self._APPROVE:
                    session = self._pending
                    self._pending = None
                    return self._apply(session)
                if normalized in self._CANCEL_COMMANDS:
                    self._pending = None
                    return "Coding Agent önerisi iptal edildi; hiçbir dosya değiştirilmedi."
                return self._pending_message()

            try:
                request = self._parser.parse(user_message)
            except Exception as error:
                return f"Coding Agent isteği geçersiz: {error} {self._USAGE}"
            if request is None:
                return self._USAGE if self._parser.is_coding_intent(user_message) else None

            try:
                architecture_plan = self._architect.plan(request.architecture_request)
                project_request = self._project_request(request, architecture_plan)
                proposal = self._prepare_proposal(request, architecture_plan, project_request)
                self._validate_scope(architecture_plan, proposal)
            except Exception as error:
                return f"Coding Agent önerisi hazırlanamadı: {error}"

            self._pending = CodingSession(request, architecture_plan, proposal)
            return self._render_preview(self._pending)

    def _prepare_proposal(
        self,
        request: CodingRequest,
        plan: ArchitecturePlan,
        project_request: ProjectEditRequest,
    ) -> ProjectEditProposal:
        deterministic = self._prepare_deterministic_edit(request, plan, project_request)
        if deterministic is not None:
            return deterministic
        return self._proposal_preparer.prepare_project_edit(project_request)

    def _prepare_deterministic_edit(
        self,
        request: CodingRequest,
        plan: ArchitecturePlan,
        project_request: ProjectEditRequest,
    ) -> ProjectEditProposal | None:
        if (
            self._deterministic_edit_parser is None
            or self._deterministic_edit_preparer is None
            or len(plan.existing_files) != 1
            or plan.new_files
        ):
            return None

        parsed = self._deterministic_edit_parser.parse(request.task)
        if parsed is None:
            parsed = SmartEditRequest(
                path=plan.existing_files[0],
                instruction=request.task,
            )
        if parsed.path.replace("\\", "/").casefold() != plan.existing_files[0].casefold():
            return None
        try:
            edit = self._deterministic_edit_preparer.prepare_smart_edit(parsed)
        except SmartEditNotApplicable:
            return None
        return ProjectEditProposal(
            instruction=project_request.instruction,
            edits=(edit,),
        )

    @staticmethod
    def _project_request(
        request: CodingRequest,
        plan: ArchitecturePlan,
    ) -> ProjectEditRequest:
        steps = "\n".join(
            f"- {step.title}: {step.description} [{', '.join(step.files)}]"
            for step in plan.steps
        )
        instruction = (
            f"USER_TASK:\n{request.task}\n\n"
            f"ARCHITECT_SUMMARY:\n{plan.summary}\n\n"
            f"ARCHITECT_STEPS:\n{steps}"
        )
        return ProjectEditRequest(
            instruction=instruction,
            existing_file_scope=plan.existing_files,
            new_file_scope=plan.new_files,
        )

    @staticmethod
    def _validate_scope(plan: ArchitecturePlan, proposal: ProjectEditProposal) -> None:
        allowed = {
            path.replace("\\", "/").casefold()
            for path in (*plan.existing_files, *plan.new_files)
        }
        targets = {
            item.path.replace("\\", "/").casefold()
            for item in (*proposal.edits, *proposal.creations)
        }
        outside = targets - allowed
        if outside:
            raise ValueError(
                "Coding Agent önerisi Architect kapsamı dışına çıktı: "
                + ", ".join(sorted(outside))
            )

    def _apply(self, session: CodingSession) -> str:
        try:
            outcome = self._proposal_applier.apply_project_edit(session.proposal)
        except Exception as error:
            return f"Coding Agent değişikliği uygulanamadı: {error}"
        paths = "\n".join(f"- {item.relative_path}" for item in outcome.outcomes)
        response = (
            f"Coding Agent değişikliği uygulandı: {len(outcome.outcomes)} dosya\n{paths}"
        )
        changed_paths = tuple(item.relative_path for item in outcome.outcomes)
        reports: list[str] = []
        if self._regression_runner is not None:
            try:
                reports.append(self._regression_runner.run_for_paths(changed_paths))
            except Exception as error:
                reports.append(
                    f"TEST AGENT RAPORU\nDurum: BAŞLATILAMADI\nHata: {error}"
                )
        if self._security_reviewer is not None:
            try:
                reports.append(self._security_reviewer.review_paths(changed_paths))
            except Exception as error:
                reports.append(
                    f"SECURITY AGENT RAPORU\nDurum: BAŞLATILAMADI\nHata: {error}"
                )
        if self._code_reviewer is not None:
            try:
                reports.append(self._code_reviewer.review_paths(changed_paths))
            except Exception as error:
                reports.append(
                    f"CODE REVIEW RAPORU\nDurum: BAŞLATILAMADI\nHata: {error}"
                )
        return "\n\n".join((response, *reports))

    def _render_preview(self, session: CodingSession) -> str:
        proposal = session.proposal
        changes = [
            f"===== EDIT {edit.path} =====\n{edit.diff.rstrip()}"
            for edit in proposal.edits
        ]
        changes.extend(
            f"===== CREATE {creation.path} =====\n{creation.content}"
            for creation in proposal.creations
        )
        combined = "\n\n".join(changes)
        truncated = len(combined) > self._preview_characters
        preview = combined[: self._preview_characters]
        suffix = "\n... (Coding Agent diff önizlemesi kısaltıldı)" if truncated else ""
        scope = ", ".join((*session.architecture_plan.existing_files, *session.architecture_plan.new_files))
        return (
            "CODING AGENT ÖNERİSİ\n\n"
            f"Mimari özet: {session.architecture_plan.summary}\n"
            f"İzin verilen dosyalar: {scope}\n"
            f"Düzenleme: {len(proposal.edits)}, yeni dosya: {len(proposal.creations)}\n"
            "Henüz hiçbir dosya değiştirilmedi.\n\n"
            f"Diff:\n{preview}{suffix}\n\n"
            f"Uygulamak için yalnızca '{self._APPROVE}', vazgeçmek için 'iptal' yaz."
        )

    def _pending_message(self) -> str:
        return (
            "Coding Agent değişikliği onay bekliyor. Uygulamak için yalnızca "
            f"'{self._APPROVE}', vazgeçmek için 'iptal' yaz."
        )
