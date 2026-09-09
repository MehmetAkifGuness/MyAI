from dataclasses import dataclass
from pathlib import Path

from boru.architecture import (
    ArchitecturePlanCache,
    CachingEditSourceWorkspace,
    LLMArchitectAgent,
    ProjectStatFingerprint,
    RuleBasedArchitectureRequestParser,
)
from boru.code_index import RelevantFileRanker, SafeCodeIndex
from boru.coding import ControlledCodingCoordinator, RuleBasedCodingRequestParser
from boru.coding.staged_applier import StagedCodingApplier
from boru.evaluation import EvidenceEvaluator
from boru.reviewing import CodeReviewAgent, PythonCodeReviewScanner, RuleBasedCodeReviewRequestParser
from boru.sandbox import DockerSandboxExecutor
from boru.security import PythonSecurityScanner, RuleBasedSecurityRequestParser, SecurityAgent
from boru.testing import RelatedTestDiscovery, RuleBasedTestAgentRequestParser, SafeTestAgent
from boru.tools import (
    BatchProjectEditApplier,
    BoundedCommandExecutor,
    CommandRisk,
    ControlledGitCoordinator,
    DependencyAwareProjectFileSelector,
    GitCommandPolicy,
    LLMProjectEditProposalPreparer,
    LLMProjectFileSelector,
    RuleBasedAssignmentEditProposalPreparer,
    RuleBasedGitRequestParser,
    RuleBasedSmartEditRequestParser,
    SafeCommandPolicy,
    SafeEditWorkspace,
    SafeProjectFileIndex,
    SafeWriteWorkspace,
    TestOutputParser,
)
from boru.tools.project_selection import RuleFirstProjectFileSelector
from boru.tools.deterministic_project_edit import (
    FallbackProjectEditProposalPreparer,
    RuleBasedStringAliasProjectEditPreparer,
)
from boru.repository.reasoning import IntelligentRepositoryTaskAnalyzer, RepositoryTaskBrief


@dataclass(slots=True)
class RepositoryWorkspaceRuntime:
    root: Path
    coding: ControlledCodingCoordinator
    evaluator: EvidenceEvaluator
    git: ControlledGitCoordinator | None
    staged_applier: StagedCodingApplier | None = None
    task_analyzer: IntelligentRepositoryTaskAnalyzer | None = None

    @property
    def has_pending(self) -> bool:
        return self.coding.has_pending or bool(self.git and self.git.has_pending)

    def validate_paths(self, paths: tuple[str, ...]) -> str:
        report = self.staged_applier.last_validation if self.staged_applier else None
        if (
            report is not None
            and set(report.paths) == set(paths)
            and self.evaluator.is_current(report)
        ):
            return report.workflow_report()
        return self.evaluator.validate_paths(paths)

    def analyze_task(self, objective: str, *, allow_clarification: bool = True) -> RepositoryTaskBrief:
        if self.task_analyzer is None:
            raise RuntimeError("Akıllı görev analizi bu sürümde etkin değil.")
        return self.task_analyzer.analyze(
            self.root, objective, allow_clarification=allow_clarification
        )


def build_repository_workspace(
    root: Path,
    chat_model,
    sandbox_image: str,
    intelligent_task_intake_enabled: bool = False,
) -> RepositoryWorkspaceRuntime:
    """Build an isolated edit/test/review pipeline rooted at one repository."""
    root = root.resolve()
    edit_workspace = SafeEditWorkspace(root)
    write_workspace = SafeWriteWorkspace(root)
    cached_workspace = CachingEditSourceWorkspace(root, edit_workspace, max_entries=256)
    code_index = SafeCodeIndex(root, max_files=2000)

    def selector(max_files: int, workspace):
        return DependencyAwareProjectFileSelector(
            base_selector=RuleFirstProjectFileSelector(
                fallback=LLMProjectFileSelector(
                    chat_model=chat_model,
                    max_files=max_files,
                    max_attempts=2,
                    context_ranker=RelevantFileRanker(code_index, max_candidates=12),
                ),
                max_files=max_files,
                deterministic_min_paths=2,
            ),
            workspace=workspace,
            max_files=max_files,
        )

    edit_index = SafeProjectFileIndex(root, max_files=2000, max_depth=12)
    architecture_index = SafeProjectFileIndex(root, max_files=2000, max_depth=12)
    edit_selector = selector(4, edit_workspace)
    architecture_selector = selector(8, cached_workspace)
    model_proposal_preparer = LLMProjectEditProposalPreparer(
        chat_model=chat_model,
        file_index=edit_index,
        file_selector=edit_selector,
        workspace=edit_workspace,
        creation_validator=write_workspace,
        max_files=4,
        max_patches_per_file=4,
        max_total_patches=12,
        max_attempts=3,
        max_source_characters=12_000,
    )
    proposal_preparer = FallbackProjectEditProposalPreparer(
        RuleBasedStringAliasProjectEditPreparer(edit_workspace),
        model_proposal_preparer,
    )
    proposal_applier = BatchProjectEditApplier(
        workspace=edit_workspace,
        creation_workspace=write_workspace,
    )
    architecture_parser = RuleBasedArchitectureRequestParser()
    architect = LLMArchitectAgent(
        chat_model=chat_model,
        file_index=architecture_index,
        file_selector=architecture_selector,
        workspace=cached_workspace,
        creation_validator=write_workspace,
        max_files=8,
        max_new_files=4,
        max_steps=12,
        max_source_characters=40_000,
        max_attempts=2,
        plan_cache=ArchitecturePlanCache(max_entries=32),
        fingerprint_provider=ProjectStatFingerprint(root),
        fast_scoped_plans=True,
    )
    sandbox = DockerSandboxExecutor(root, sandbox_image)
    evaluator = EvidenceEvaluator(root, sandbox, max_paths=12)
    tests = SafeTestAgent(
        parser=RuleBasedTestAgentRequestParser(),
        discovery=RelatedTestDiscovery(root),
        policy=SafeCommandPolicy(),
        executor=sandbox,
        result_parser=TestOutputParser(),
    )
    security = SecurityAgent(
        parser=RuleBasedSecurityRequestParser(),
        scanner=PythonSecurityScanner(root),
    )
    review = CodeReviewAgent(
        parser=RuleBasedCodeReviewRequestParser(),
        scanner=PythonCodeReviewScanner(root),
    )

    def staged_evaluator(staged_root: Path):
        return EvidenceEvaluator(
            staged_root,
            DockerSandboxExecutor(staged_root, sandbox_image),
            max_paths=12,
        )

    staged_applier = StagedCodingApplier(root, staged_evaluator, proposal_applier)
    coding = ControlledCodingCoordinator(
        parser=RuleBasedCodingRequestParser(architecture_parser),
        architect=architect,
        proposal_preparer=proposal_preparer,
        proposal_applier=staged_applier,
        deterministic_edit_parser=RuleBasedSmartEditRequestParser(),
        deterministic_edit_preparer=RuleBasedAssignmentEditProposalPreparer(
            workspace=edit_workspace
        ),
        regression_runner=tests,
        security_reviewer=security,
        code_reviewer=review,
        quality_evaluator=evaluator,
        max_staged_repairs=1,
    )
    git = None
    if (root / ".git").is_dir():
        git = ControlledGitCoordinator(
            RuleBasedGitRequestParser(),
            GitCommandPolicy(),
            BoundedCommandExecutor(
                root,
                timeout_seconds=120,
                max_output_bytes=1024 * 1024,
                allowed_risks=(CommandRisk.SAFE, CommandRisk.REQUIRES_APPROVAL),
            ),
        )
    analyzer = IntelligentRepositoryTaskAnalyzer() if intelligent_task_intake_enabled else None
    return RepositoryWorkspaceRuntime(root, coding, evaluator, git, staged_applier, analyzer)
