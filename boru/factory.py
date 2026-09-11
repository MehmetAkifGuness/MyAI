from pathlib import Path
import os

from boru.sandbox import DockerSandboxExecutor, TargetedSandboxTestTool
from boru.sandbox.coordinator import SandboxCoordinator
from boru.evaluation import EvidenceEvaluator, EvaluationCoordinator
from boru.improvement import (
    GoalDrivenChangeScopeResolver,
    ImprovementCoordinator,
    NaturalLanguageImprovementCoordinator,
    SafeChangeScopeResolver,
    VerifiedImprovementApplier,
)
from boru.agent import GeneralAgentCoordinator, ReadOnlyToolAgent
from boru.code_index import (
    CodeSearchTool,
    DependencyGraphCoordinator,
    FileSymbolsTool,
    ImpactAnalysisTool,
    ProjectOverviewTool,
    RelatedCodeTool,
    RelevantFileRanker,
    SafeCodeIndex,
    SafeCodeImpactIndex,
    SafeCodeRelationshipIndex,
)

from boru.architecture import (
    ArchitectCoordinator,
    ArchitecturePlanCache,
    CachingEditSourceWorkspace,
    LLMArchitectAgent,
    ProjectStatFingerprint,
    RuleBasedArchitectureRequestParser,
)
from boru.api_tools import (
    BoundedHttpApiClient,
    ControlledApiCoordinator,
    RuleBasedApiRequestParser,
    SafeApiPolicy,
)
from boru.assistant import (
    AssistantService,
)
from boru.context import (
    AutonomousWebGroundingContextProvider,
    SystemClockContextProvider,
)
from boru.coding import (
    ControlledCodingCoordinator,
    RuleBasedCodingRequestParser,
)
from boru.config import (
    AppSettings,
)
from boru.context import (
    ConversationContextBuilder,
)
from boru.database_tools import (
    DatabaseReadCoordinator,
    ReadOnlySqliteService,
    RuleBasedDatabaseRequestParser,
)
from boru.conversation import (
    ConversationHistory,
)
from boru.memory import (
    AliasAwareSubjectMatcher,
    ConservativeMemoryDecisionGate,
    DEFAULT_SUBJECT_ALIAS_GROUPS,
    ExplicitMemoryExtractor,
    GroundedMemoryDecisionEngine,
    HybridMemoryRetriever,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LLMMemoryDecisionEngine,
    LongTermMemoryService,
    MemoryContextProvider,
    MemoryObserver,
    OllamaEmbeddingProvider,
    RelevantMemoryQueryResolver,
    RuleBasedMemoryForgetParser,
    RuleBasedMemoryForgetResolver,
    RuleBasedMemoryIntentDetector,
    RuleBasedMemoryQueryResolver,
    RuleBasedMemoryStructurer,
    SemanticMemoryRetriever,
    ExactSubjectMatcher,
    SemanticSubjectMatcher,
    SubjectRelationConflictResolver,
)
from boru.knowledge import (
    HybridKnowledgeRetriever,
    JsonKnowledgeRepository,
    KnowledgeCoordinator,
    KnowledgeService,
    RuleBasedKnowledgeRequestParser,
    SafeKnowledgeDocumentLoader,
    TextKnowledgeChunker,
)
from boru.ollama_model import (
    OllamaChatModel,
)
from boru.modeling import StructuredModelCascade
from boru.orchestration import (
    AgentOrchestrator,
    RuleBasedOrchestrationRequestParser,
)
from boru.performance import (
    ModelWarmupService,
    PerformanceMonitor,
    PerformanceStatusCoordinator,
)
from boru.profile import (
    JsonUserProfileRepository,
    ProfileContextProvider,
    ProfileObserver,
    RuleBasedProfileExtractor,
    RuleBasedProfileQueryResolver,
    UserProfileService,
)
from boru.project_memory import (
    JsonProjectMemoryRepository,
    ProjectMemoryContextProvider,
    ProjectMemoryCoordinator,
    ProjectMemoryService,
    RuleBasedProjectMemoryParser,
)
from boru.prompts import (
    SystemPromptFactory,
)
from boru.reviewing import (
    CodeReviewAgent,
    PythonCodeReviewScanner,
    RuleBasedCodeReviewRequestParser,
)
from boru.security import (
    PythonSecurityScanner,
    RuleBasedSecurityRequestParser,
    SecurityAgent,
)
from boru.tools import (
    BoundedCommandExecutor,
    CalculatorTool,
    CommandRisk,
    ChainedToolPlanner,
    CompositeToolResultSynthesizer,
    ControlledAutoFixCoordinator,
    ControlledGitCoordinator,
    ControlledWriteCoordinator,
    CurrentTimeTool,
    DirectoryCountSynthesisResolver,
    DependencyAwareProjectFileSelector,
    EditFileTool,
    ExclusiveOperationCoordinator,
    FallbackSmartEditProposalPreparer,
    FallbackToolPlanner,
    GroundedLLMToolResultSynthesizer,
    GitCommandPolicy,
    LLMToolPlanner,
    LLMProjectEditProposalPreparer,
    LLMProjectFileSelector,
    LLMSmartEditProposalPreparer,
    ListDirectoryTool,
    NaturalLanguageToolPlanner,
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    RuleBasedCommandRequestParser,
    RuleBasedProjectEditRequestParser,
    RuleBasedAssignmentEditProposalPreparer,
    RuleBasedAutoFixRequestParser,
    RuleBasedEditRequestParser,
    RuleBasedFilesystemOperationParser,
    RuleBasedGitRequestParser,
    RuleBasedSmartEditRequestParser,
    RuleBasedToolCandidateDetector,
    RuleBasedToolPlanner,
    RuleBasedWriteIntentDetector,
    RuleBasedWriteRequestParser,
    SafeEditWorkspace,
    SafeCommandCoordinator,
    SafeCommandPolicy,
    SafeFilesystemOperationWorkspace,
    SafeProjectFileIndex,
    SafeWriteWorkspace,
    ShellEnvironmentAssignmentGuard,
    BatchProjectEditApplier,
    ToolCoordinator,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
    TestOutputParser,
    WriteFileTool,
)
from boru.tools.project_selection import (
    RuleFirstProjectFileSelector,
)
from boru.testing import (
    AutoTestGeneratorCoordinator,
    RelatedTestDiscovery,
    RuleBasedTestAgentRequestParser,
    SafeTestAgent,
)
from boru.tasks import (
    ArchitectureTaskPlanner,
    JsonTaskCheckpointRepository,
    PersistentTaskPlanState,
    RuleBasedTaskCommandParser,
    TaskPlanCoordinator,
    TaskSourceFingerprintGuard,
)
from boru.tasks.managed_checkpoint import ManagedTaskCheckpointRepository
from boru.tasks.reliable_state import ReliableTaskPlanState
from boru.tasks.reliable_coordinator import ReliableTaskCoordinator
from boru.tasks.workflow_guard import GuardedTaskWorkflow
from boru.sandbox.terminal import SandboxTerminalCoordinator
from boru.sandbox.history import TerminalHistory
from boru.autonomy import AutonomousDevelopmentCoordinator
from boru.tasks.repair import RepairProposalGuard, TaskRepairController
from boru.coding.staged_applier import StagedCodingApplier
from boru.benchmark import BenchmarkCoordinator
from boru.benchmark.runner import CodingBenchmark
from boru.repository import (
    GitHubRepositoryImporter,
    RepositoryAuditLog,
    RepositoryCoordinator,
    RepositoryInspector,
    RepositoryWorkspaceState,
    build_repository_workspace,
)
from boru.ui import (
    ChatAppUI,
)


def _resolve_project_path(
    configured_path: str,
    base_dir: Path | None = None,
) -> Path:
    path = Path(
        configured_path
    )

    if path.is_absolute():
        return path

    root = (
        base_dir
        if base_dir is not None
        else (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )
    )
    return root / path


def _build_memory_components(
    settings: AppSettings,
):
    keyword_retriever = (
        KeywordMemoryRetriever()
    )

    if not settings.memory_semantic_enabled:
        subject_matcher = (
            AliasAwareSubjectMatcher(
                delegate=ExactSubjectMatcher(),
                alias_groups=(
                    DEFAULT_SUBJECT_ALIAS_GROUPS
                ),
            )
        )

        return (
            keyword_retriever,
            SubjectRelationConflictResolver(
                subject_matcher=(
                    subject_matcher
                )
            ),
            subject_matcher,
        )

    embedding_provider = (
        OllamaEmbeddingProvider(
            settings.memory_embedding_model
        )
    )

    semantic_retriever = (
        SemanticMemoryRetriever(
            embedding_provider=(
                embedding_provider
            ),
            minimum_similarity=(
                settings
                .memory_semantic_min_similarity
            ),
        )
    )

    hybrid_retriever = (
        HybridMemoryRetriever(
            keyword_retriever=(
                keyword_retriever
            ),
            semantic_retriever=(
                semantic_retriever
            ),
        )
    )

    semantic_subject_matcher = (
        SemanticSubjectMatcher(
            embedding_provider=(
                embedding_provider
            ),
            minimum_similarity=(
                settings
                .memory_subject_identity_min_similarity
            ),
        )
    )

    subject_matcher = (
        AliasAwareSubjectMatcher(
            delegate=(
                semantic_subject_matcher
            ),
            alias_groups=(
                DEFAULT_SUBJECT_ALIAS_GROUPS
            ),
        )
    )

    conflict_resolver = (
        SubjectRelationConflictResolver(
            subject_matcher=(
                subject_matcher
            )
        )
    )

    return (
        hybrid_retriever,
        conflict_resolver,
        subject_matcher,
    )


def build_application(
    *,
    application_version: str = "V0.17",
    startup_message: str | None = None,
    structured_timeout_seconds: float = 180.0,
    structured_num_predict: int = 384,
    architect_max_attempts: int = 3,
    architect_fast_scoped_plans: bool = False,
    coding_agent_enabled: bool = False,
    test_agent_enabled: bool = False,
    security_agent_enabled: bool = False,
    code_review_agent_enabled: bool = False,
    orchestrator_enabled: bool = False,
    task_system_enabled: bool = False,
    project_memory_enabled: bool = False,
    knowledge_rag_enabled: bool = False,
    external_tools_enabled: bool = False,
    sandbox_enabled: bool = False,
    evaluation_enabled: bool = False,
    improvement_enabled: bool = False,
    general_agent_enabled: bool = False,
    deep_code_index_enabled: bool = False,
    natural_change_enabled: bool = False,
    goal_driven_change_enabled: bool = False,
    impact_analysis_enabled: bool = False,
    runtime_test_agent_enabled: bool = False,
    runtime_repair_enabled: bool = False,
    batch_runtime_repair_enabled: bool = False,
    planned_task_execution_enabled: bool = False,
    persistent_task_checkpoint_enabled: bool = False,
    source_drift_detection_enabled: bool = False,
    reliable_tasks_enabled: bool = False,
    sandbox_terminal_enabled: bool = False,
    autonomous_development_enabled: bool = False,
    autonomy_feature_level: int = 0,
    staged_coding_enabled: bool = False,
    reliable_structured_calls_enabled: bool = False,
    relevant_context_enabled: bool = False,
    staged_feedback_repair_enabled: bool = False,
    benchmark_chat_enabled: bool = False,
    adaptive_model_routing_enabled: bool = False,
    repository_intelligence_enabled: bool = False,
    repository_workspace_enabled: bool = False,
    intelligent_task_intake_enabled: bool = False,
    deep_reasoning_enabled: bool = False,
    web_research_enabled: bool = False,
    conversation_quality_enabled: bool = False,
    terminal_feature_level: int = 0,
    project_edit_max_attempts: int = 2,
    project_root: Path | None = None,
) -> ChatAppUI:
    if project_root is None:
        project_root = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )
    else:
        project_root = Path(project_root).resolve()

    def _resolve_path(p: str) -> Path:
        return _resolve_project_path(p, base_dir=project_root)

    if natural_change_enabled and not improvement_enabled:
        raise ValueError("Doğal dil değişiklik akışı kontrollü iyileştirme gerektirir.")
    if goal_driven_change_enabled and (
        not natural_change_enabled or not deep_code_index_enabled
    ):
        raise ValueError(
            "Hedef odaklı değişiklik akışı doğal değişiklik ve ilişki indeksi gerektirir."
        )
    if impact_analysis_enabled and (
        not general_agent_enabled or not deep_code_index_enabled
    ):
        raise ValueError("Etki analizi güvenli ilişki indeksi gerektirir.")
    if runtime_test_agent_enabled and (
        not general_agent_enabled or not sandbox_enabled
    ):
        raise ValueError("Çalışma zamanı test ajanı genel ajan ve Docker sandbox gerektirir.")
    if runtime_repair_enabled and (
        not runtime_test_agent_enabled or not goal_driven_change_enabled
    ):
        raise ValueError(
            "Çalışma zamanı onarımı hedefli test ajanı ve hedef odaklı değişiklik gerektirir."
        )
    if batch_runtime_repair_enabled and not runtime_repair_enabled:
        raise ValueError("Çoklu çalışma zamanı onarımı tekli onarım akışını gerektirir.")
    if planned_task_execution_enabled and not task_system_enabled:
        raise ValueError("Planlı görev yürütme Task/Plan sistemini gerektirir.")
    if persistent_task_checkpoint_enabled and not planned_task_execution_enabled:
        raise ValueError("Kalıcı task checkpoint planlı görev yürütmeyi gerektirir.")
    if source_drift_detection_enabled and not persistent_task_checkpoint_enabled:
        raise ValueError("Kaynak drift denetimi kalıcı task checkpoint gerektirir.")
    if reliable_tasks_enabled and not source_drift_detection_enabled:
        raise ValueError("Güvenilir görev yürütme kaynak drift denetimi gerektirir.")
    if sandbox_terminal_enabled and not sandbox_enabled:
        raise ValueError("Terminal Docker sandbox gerektirir.")
    if type(terminal_feature_level) is not int or not 0 <= terminal_feature_level <= 9:
        raise ValueError("Terminal özellik seviyesi 0-9 arasında olmalıdır.")
    if terminal_feature_level and not sandbox_terminal_enabled:
        raise ValueError("Terminal özellikleri sandbox terminal gerektirir.")
    if autonomous_development_enabled and not reliable_tasks_enabled:
        raise ValueError("Otonom geliştirme güvenilir görev yürütme gerektirir.")
    if type(autonomy_feature_level) is not int or not 0 <= autonomy_feature_level <= 13:
        raise ValueError("Otonomi özellik seviyesi 0-13 arasında olmalıdır.")
    if autonomy_feature_level and not autonomous_development_enabled:
        raise ValueError("Otonomi özellikleri otonom geliştirme akışını gerektirir.")
    if autonomy_feature_level >= 11 and not evaluation_enabled:
        raise ValueError("Task teşhisi ve onarımı kanıt değerlendiricisi gerektirir.")
    if staged_coding_enabled and not (coding_agent_enabled and sandbox_enabled and evaluation_enabled):
        raise ValueError("Geçici kopya doğrulaması Coding, sandbox ve değerlendirme gerektirir.")
    if reliable_structured_calls_enabled and not general_agent_enabled:
        raise ValueError("Structured yeniden deneme genel ajanı gerektirir.")
    if relevant_context_enabled and not general_agent_enabled:
        raise ValueError("Akıllı bağlam seçimi kod indeksini gerektirir.")
    if staged_feedback_repair_enabled and not staged_coding_enabled:
        raise ValueError("Test geri bildirimli onarım geçici kopya doğrulamasını gerektirir.")
    if benchmark_chat_enabled and not sandbox_enabled:
        raise ValueError("Sohbet benchmarkı Docker sandbox gerektirir.")

    if adaptive_model_routing_enabled and not reliable_structured_calls_enabled:
        raise ValueError("Uyarlamalı model yönlendirme structured yeniden deneme gerektirir.")

    if repository_workspace_enabled and not (repository_intelligence_enabled and sandbox_enabled):
        raise ValueError("Repo çalışma alanı repo zekâsı ve Docker sandbox gerektirir.")
    if intelligent_task_intake_enabled and not repository_workspace_enabled:
        raise ValueError("Akıllı görev anlama repo çalışma alanı gerektirir.")
    if deep_reasoning_enabled and not intelligent_task_intake_enabled:
        raise ValueError('Derin araştırma akıllı görev anlama gerektirir.')

    settings = (
        AppSettings.from_env()
    )

    performance_monitor = (
        PerformanceMonitor()
    )

    primary_chat_model = OllamaChatModel(
            settings.model_name,
            structured_thinking=False if deep_reasoning_enabled and settings.model_name.startswith('qwen3') else None,
            request_timeout_seconds=180,
            structured_timeout_seconds=structured_timeout_seconds,
            structured_num_predict=structured_num_predict,
            keep_alive="10m",
            performance_monitor=(
                performance_monitor
            ),
        )
    if adaptive_model_routing_enabled and settings.fallback_model_name:
        chat_model = StructuredModelCascade(
            primary_chat_model,
            OllamaChatModel(
                settings.fallback_model_name,
                structured_thinking=False if deep_reasoning_enabled and settings.fallback_model_name.startswith('qwen3') else None,
                request_timeout_seconds=180,
                structured_timeout_seconds=structured_timeout_seconds,
                structured_num_predict=structured_num_predict,
                keep_alive="10m",
                performance_monitor=performance_monitor,
            ),
        )
    else:
        chat_model = primary_chat_model

    history = (
        ConversationHistory(
            max_turns=(
                settings.history_turns
            )
        )
    )

    context_builder = (
        ConversationContextBuilder(
            max_turn_characters=4000 if conversation_quality_enabled else None,
            max_turns=(
                settings.context_turns
            ),
            max_characters=(
                settings
                .context_max_characters
            ),
        )
    )

    profile_service = (
        UserProfileService(
            repository=(
                JsonUserProfileRepository(
                    _resolve_path(
                        settings.profile_path
                    )
                )
            ),
            extractor=(
                RuleBasedProfileExtractor()
            ),
        )
    )

    memory_forget_parser = (
        RuleBasedMemoryForgetParser()
    )

    memory_decision_engine = None
    memory_decision_gate = None

    if settings.memory_auto_capture:
        memory_decision_engine = (
            GroundedMemoryDecisionEngine(
                LLMMemoryDecisionEngine(
                    chat_model
                )
            )
        )

        memory_decision_gate = (
            ConservativeMemoryDecisionGate(
                forget_parser=(
                    memory_forget_parser
                )
            )
        )

    memory_intent_detector = (
        RuleBasedMemoryIntentDetector(history if conversation_quality_enabled else None)
    )

    (
        memory_retriever,
        memory_conflict_resolver,
        memory_subject_matcher,
    ) = _build_memory_components(
        settings
    )

    memory_service = (
        LongTermMemoryService(
            repository=(
                JsonMemoryRepository(
                    _resolve_path(
                        settings.memory_path
                    )
                )
            ),
            extractor=(
                ExplicitMemoryExtractor()
            ),
            retriever=(
                memory_retriever
            ),
            context_limit=(
                settings
                .memory_context_limit
            ),
            decision_engine=(
                memory_decision_engine
            ),
            decision_gate=(
                memory_decision_gate
            ),
            structurer=(
                RuleBasedMemoryStructurer()
            ),
            conflict_resolver=(
                memory_conflict_resolver
            ),
            subject_matcher=(
                memory_subject_matcher
            ),
        )
    )

    memory_forget_resolver = (
        RuleBasedMemoryForgetResolver(
            memory_service=(
                memory_service
            ),
            parser=(
                memory_forget_parser
            ),
        )
    )

    read_workspace = (
        ReadOnlyWorkspace(
            project_root
        )
    )

    code_index = None
    relationship_index = None
    impact_index = None
    read_tools = [
        CalculatorTool(),
        CurrentTimeTool(),
        ListDirectoryTool(read_workspace),
        ReadFileTool(read_workspace),
    ]
    if general_agent_enabled:
        code_index = SafeCodeIndex(project_root)
        read_tools.extend(
            [
                ProjectOverviewTool(code_index),
                CodeSearchTool(code_index),
                FileSymbolsTool(code_index),
            ]
        )
        if deep_code_index_enabled:
            relationship_index = SafeCodeRelationshipIndex(project_root)
            read_tools.append(
                RelatedCodeTool(relationship_index)
            )
        if impact_analysis_enabled:
            impact_index = SafeCodeImpactIndex(project_root)
            read_tools.append(ImpactAnalysisTool(impact_index))

    read_registry = ToolRegistry(read_tools)

    read_executor = ToolExecutor(
        registry=read_registry,
        policy=RiskBasedToolPolicy(
            allowed_risks=(
                ToolRisk.SAFE,
                ToolRisk.READ_ONLY,
                *(
                    (ToolRisk.EXECUTION,)
                    if runtime_test_agent_enabled
                    else ()
                ),
            )
        ),
    )

    general_agent_coordinator = None
    if general_agent_enabled:
        general_agent_coordinator = GeneralAgentCoordinator(
            ReadOnlyToolAgent(
                model=chat_model,
                registry=read_registry,
                executor=read_executor,
                performance_monitor=performance_monitor,
                structured_attempts=2 if reliable_structured_calls_enabled else 1,
            )
        )

    read_planner = (
        FallbackToolPlanner(
            primary=(
                ChainedToolPlanner(
                    [
                        RuleBasedToolPlanner(),
                        NaturalLanguageToolPlanner(),
                    ]
                )
            ),
            fallback=(
                LLMToolPlanner(
                    chat_model=(
                        chat_model
                    ),
                    registry=(
                        read_registry
                    ),
                )
            ),
            candidate_detector=(
                RuleBasedToolCandidateDetector()
            ),
        )
    )

    read_tool_coordinator = (
        ToolCoordinator(
            planner=read_planner,
            executor=read_executor,
            synthesizer=(
                CompositeToolResultSynthesizer(
                    resolvers=[
                        DirectoryCountSynthesisResolver(),
                    ],
                    fallback=(
                        GroundedLLMToolResultSynthesizer(
                            chat_model
                        )
                    ),
                )
            ),
        )
    )

    write_workspace = (
        SafeWriteWorkspace(
            project_root
        )
    )

    edit_workspace = (
        SafeEditWorkspace(
            project_root
        )
    )

    architect_workspace = (
        CachingEditSourceWorkspace(
            project_root,
            edit_workspace,
            max_entries=256,
            monitor=(
                performance_monitor
            ),
        )
    )

    filesystem_workspace = (
        SafeFilesystemOperationWorkspace(
            project_root
        )
    )

    write_registry = ToolRegistry(
        [
            WriteFileTool(
                write_workspace
            ),
            EditFileTool(
                edit_workspace
            ),
        ]
    )

    write_executor = ToolExecutor(
        registry=write_registry,
        policy=RiskBasedToolPolicy(
            allowed_risks=(
                ToolRisk.WRITE,
            )
        ),
    )

    deterministic_assignment_preparer = RuleBasedAssignmentEditProposalPreparer(
        workspace=edit_workspace
    )
    smart_edit_preparer = (
        FallbackSmartEditProposalPreparer(
            primary=(
                deterministic_assignment_preparer
            ),
            fallback=(
                LLMSmartEditProposalPreparer(
                    chat_model=(
                        chat_model
                    ),
                    workspace=(
                        edit_workspace
                    ),
                    max_attempts=3,
                )
            ),
        )
    )

    project_file_index = (
        SafeProjectFileIndex(
            project_root,
            max_files=200,
            max_depth=8,
        )
    )

    architect_file_index = (
        SafeProjectFileIndex(
            project_root,
            max_files=400,
            max_depth=8,
        )
    )

    project_file_selector = (
        DependencyAwareProjectFileSelector(
            base_selector=(
                RuleFirstProjectFileSelector(
                    fallback=(
                        LLMProjectFileSelector(
                            chat_model=(
                                chat_model
                            ),
                            max_files=4,
                            max_attempts=2,
                            context_ranker=(
                                RelevantFileRanker(code_index)
                                if relevant_context_enabled else None
                            ),
                        )
                    ),
                    max_files=4,
                    deterministic_min_paths=2,
                )
            ),
            workspace=(
                edit_workspace
            ),
            max_files=4,
        )
    )

    architect_file_selector = (
        DependencyAwareProjectFileSelector(
            base_selector=(
                RuleFirstProjectFileSelector(
                    fallback=(
                        LLMProjectFileSelector(
                            chat_model=(
                                chat_model
                            ),
                            max_files=8,
                            max_attempts=2,
                            context_ranker=(
                                RelevantFileRanker(code_index)
                                if relevant_context_enabled else None
                            ),
                        )
                    ),
                    max_files=8,
                    deterministic_min_paths=2,
                )
            ),
            workspace=(
                architect_workspace
            ),
            max_files=8,
        )
    )

    project_edit_preparer = (
        LLMProjectEditProposalPreparer(
            chat_model=(
                chat_model
            ),
            file_index=(
                project_file_index
            ),
            file_selector=(
                project_file_selector
            ),
            workspace=(
                edit_workspace
            ),
            creation_validator=(
                write_workspace
            ),
            max_files=4,
            max_patches_per_file=4,
            max_total_patches=12,
            max_attempts=project_edit_max_attempts,
        )
    )

    project_edit_applier = (
        BatchProjectEditApplier(
            workspace=(
                edit_workspace
            ),
            creation_workspace=(
                write_workspace
            ),
        )
    )

    controlled_write = (
        ControlledWriteCoordinator(
            parser=(
                RuleBasedWriteRequestParser()
            ),
            intent_detector=(
                RuleBasedWriteIntentDetector()
            ),
            executor=(
                write_executor
            ),
            edit_parser=(
                RuleBasedEditRequestParser()
            ),
            edit_preparer=(
                edit_workspace
            ),
            smart_edit_parser=(
                RuleBasedSmartEditRequestParser()
            ),
            smart_edit_preparer=(
                smart_edit_preparer
            ),
            project_edit_parser=(
                RuleBasedProjectEditRequestParser()
            ),
            project_edit_preparer=(
                project_edit_preparer
            ),
            project_edit_applier=(
                project_edit_applier
            ),
            filesystem_parser=(
                RuleBasedFilesystemOperationParser()
            ),
            filesystem_workspace=(
                filesystem_workspace
            ),
        )
    )

    command_policy = SafeCommandPolicy()
    command_executor = BoundedCommandExecutor(
        project_root,
        timeout_seconds=120,
        max_output_bytes=1024 * 1024,
    )
    sandbox_executor = None
    evaluator = None
    sandbox_image = os.getenv("BORU_SANDBOX_IMAGE", "boru-sandbox:1.0")
    if sandbox_enabled:
        sandbox_executor = DockerSandboxExecutor(project_root, sandbox_image)
        command_executor = sandbox_executor
    if runtime_test_agent_enabled:
        if sandbox_executor is None:
            raise ValueError("Çalışma zamanı test aracı Docker sandbox gerektirir.")
        read_registry.register(
            TargetedSandboxTestTool(project_root, sandbox_executor)
        )
    if evaluation_enabled:
        if sandbox_executor is None:
            raise ValueError("Öz değerlendirme sandbox gerektirir.")
        evaluator = EvidenceEvaluator(
            project_root,
            command_executor,
            max_paths=12 if batch_runtime_repair_enabled else 8,
        )
    test_output_parser = TestOutputParser()
    command_coordinator = (
        SafeCommandCoordinator(
            parser=(
                RuleBasedCommandRequestParser()
            ),
            policy=command_policy,
            executor=command_executor,
            result_parser=test_output_parser,
        )
    )

    test_agent = None
    if test_agent_enabled:
        test_agent = SafeTestAgent(
            parser=RuleBasedTestAgentRequestParser(),
            discovery=RelatedTestDiscovery(project_root),
            policy=command_policy,
            executor=command_executor,
            result_parser=test_output_parser,
        )

    security_agent = None
    if security_agent_enabled:
        security_agent = SecurityAgent(
            parser=RuleBasedSecurityRequestParser(),
            scanner=PythonSecurityScanner(project_root),
        )

    code_review_agent = None
    if code_review_agent_enabled:
        code_review_agent = CodeReviewAgent(
            parser=RuleBasedCodeReviewRequestParser(),
            scanner=PythonCodeReviewScanner(project_root),
        )

    git_coordinator = (
        ControlledGitCoordinator(
            parser=(
                RuleBasedGitRequestParser()
            ),
            policy=(
                GitCommandPolicy()
            ),
            executor=(
                BoundedCommandExecutor(
                    project_root,
                    timeout_seconds=120,
                    max_output_bytes=(
                        1024 * 1024
                    ),
                    allowed_risks=(
                        CommandRisk.SAFE,
                        CommandRisk.REQUIRES_APPROVAL,
                    ),
                )
            ),
        )
    )

    auto_fix_coordinator = (
        ControlledAutoFixCoordinator(
            parser=(
                RuleBasedAutoFixRequestParser(
                    RuleBasedCommandRequestParser()
                )
            ),
            command_policy=(
                SafeCommandPolicy()
            ),
            command_executor=command_executor,
            result_parser=(
                TestOutputParser()
            ),
            proposal_preparer=(
                project_edit_preparer
            ),
            proposal_applier=(
                project_edit_applier
            ),
            max_fix_attempts=3,
        )
    )

    architecture_request_parser = RuleBasedArchitectureRequestParser()
    architect_agent = (
        LLMArchitectAgent(
            chat_model=(
                chat_model
            ),
            file_index=(
                architect_file_index
            ),
            file_selector=(
                architect_file_selector
            ),
            workspace=(
                architect_workspace
            ),
            creation_validator=(
                write_workspace
            ),
            max_files=8,
            max_new_files=4,
            max_steps=12,
            max_source_characters=40000,
            max_attempts=architect_max_attempts,
            plan_cache=(
                ArchitecturePlanCache(
                    max_entries=32,
                    monitor=(
                        performance_monitor
                    ),
                )
            ),
            fingerprint_provider=(
                ProjectStatFingerprint(
                    project_root
                )
            ),
            performance_monitor=(
                performance_monitor
            ),
            fast_scoped_plans=architect_fast_scoped_plans,
        )
    )
    architect_coordinator = (
        ArchitectCoordinator(
            parser=architecture_request_parser,
            planner=architect_agent,
        )
    )

    repair_guard = RepairProposalGuard(evaluator) if autonomy_feature_level >= 11 else None
    def staged_evaluator(root):
        return EvidenceEvaluator(root, DockerSandboxExecutor(root, sandbox_image),
                                 max_paths=12 if batch_runtime_repair_enabled else 8)

    coding_applier = (
        StagedCodingApplier(project_root, staged_evaluator, project_edit_applier)
        if staged_coding_enabled else project_edit_applier
    )
    coding_coordinator = None
    if coding_agent_enabled:
        coding_coordinator = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(
                architecture_request_parser
            ),
            architect=architect_agent,
            proposal_preparer=project_edit_preparer,
            proposal_applier=coding_applier,
            deterministic_edit_parser=RuleBasedSmartEditRequestParser(),
            deterministic_edit_preparer=deterministic_assignment_preparer,
            regression_runner=test_agent,
            security_reviewer=security_agent,
            code_reviewer=code_review_agent,
            quality_evaluator=evaluator,
            proposal_guard=repair_guard,
            max_staged_repairs=1 if staged_feedback_repair_enabled else 0,
        )

    coding_operation = coding_coordinator
    agent_orchestrator = None
    if orchestrator_enabled:
        if coding_coordinator is None:
            raise ValueError("Agent Orchestrator için Coding Agent etkin olmalıdır.")
        if test_agent is None or security_agent is None or code_review_agent is None:
            raise ValueError(
                "Agent Orchestrator için Test, Security ve Code Review ajanları "
                "etkin olmalıdır."
            )
        agent_orchestrator = AgentOrchestrator(
            parser=RuleBasedOrchestrationRequestParser(),
            coding_workflow=coding_coordinator,
        )
        coding_operation = agent_orchestrator

    if task_system_enabled:
        if agent_orchestrator is None:
            raise ValueError("Task sistemi için Agent Orchestrator etkin olmalıdır.")
        task_state = None
        task_repository = None
        if reliable_tasks_enabled:
            task_repository = ManagedTaskCheckpointRepository(
                _resolve_path(settings.task_checkpoint_path),
                lock_path=project_root / "data" / "task_project.lock",
            )
            task_state = ReliableTaskPlanState(task_repository, TaskSourceFingerprintGuard(project_root))
            agent_orchestrator = GuardedTaskWorkflow(agent_orchestrator, task_state)
        elif persistent_task_checkpoint_enabled:
            task_state = PersistentTaskPlanState(
                JsonTaskCheckpointRepository(
                    _resolve_path(settings.task_checkpoint_path)
                ),
                TaskSourceFingerprintGuard(project_root)
                if source_drift_detection_enabled
                else None,
            )
        coding_operation = TaskPlanCoordinator(
            parser=RuleBasedTaskCommandParser(),
            planner=ArchitectureTaskPlanner(
                architect_agent,
                architecture_request_parser,
                preserve_objective_context=planned_task_execution_enabled,
            ),
            workflow=agent_orchestrator,
            state=task_state,
            planned_execution_enabled=planned_task_execution_enabled,
        )
        if reliable_tasks_enabled:
            repair = (
                TaskRepairController(task_state, coding_operation, evaluator,
                                     RelatedTestDiscovery(project_root), repair_guard)
                if repair_guard is not None else None
            )
            coding_operation = ReliableTaskCoordinator(
                coding_operation,
                task_state,
                task_repository,
                evaluator=evaluator,
                repair=repair,
            )
        if autonomous_development_enabled:
            coding_operation = AutonomousDevelopmentCoordinator(
                coding_operation,
                evaluator=evaluator,
                feature_level=autonomy_feature_level,
            )

    operation_resolvers = [
        ShellEnvironmentAssignmentGuard(),
        auto_fix_coordinator,
        controlled_write,
        git_coordinator,
    ]
    if sandbox_terminal_enabled:
        operation_resolvers.insert(
            0,
            SandboxTerminalCoordinator(
                project_root,
                sandbox_executor,
                (
                    TerminalHistory(project_root / "data" / "terminal_history.json")
                    if terminal_feature_level >= 2
                    else None
                ),
                feature_level=terminal_feature_level,
            ),
        )
    if benchmark_chat_enabled:
        operation_resolvers.insert(
            0,
            BenchmarkCoordinator(
                project_root,
                runner_factory=lambda repair_attempts: CodingBenchmark(
                    lambda root: DockerSandboxExecutor(root, sandbox_image),
                    repair_attempts=repair_attempts,
                ),
                model_factory=lambda name: OllamaChatModel(
                    name,
                    structured_thinking=False if deep_reasoning_enabled and name.startswith('qwen3') else None,
                    structured_timeout_seconds=structured_timeout_seconds,
                    structured_num_predict=structured_num_predict,
                ),
            ),
        )
    if repository_intelligence_enabled:
        operation_resolvers.insert(
            0,
            RepositoryCoordinator(
                project_root,
                RepositoryInspector(),
                GitHubRepositoryImporter(project_root),
                workspace_factory=(
                    (lambda root: build_repository_workspace(
                        root,
                        chat_model,
                        sandbox_image,
                        intelligent_task_intake_enabled=intelligent_task_intake_enabled,
                        deep_reasoning_enabled=deep_reasoning_enabled,
                        experience_directory=project_root / 'data' / 'verified_experience',
                    ))
                    if repository_workspace_enabled else None
                ),
                workspace_state=(
                    RepositoryWorkspaceState(project_root / "data" / "repository_workspace.json")
                    if repository_workspace_enabled else None
                ),
                audit_log=(
                    RepositoryAuditLog(project_root / "data" / "repository_audit.json")
                    if repository_workspace_enabled else None
                ),
            ),
        )
    if improvement_enabled:
        if evaluator is None or coding_coordinator is None:
            raise ValueError("İyileştirme Coding, değerlendirme ve sandbox gerektirir.")
        improvement_applier = VerifiedImprovementApplier(project_root, staged_evaluator)
        improvement_coding = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(architecture_request_parser),
            architect=architect_agent,
            proposal_preparer=project_edit_preparer,
            proposal_applier=improvement_applier,
            proposal_guard=improvement_applier.validate_proposal,
            deterministic_edit_parser=RuleBasedSmartEditRequestParser(),
            deterministic_edit_preparer=deterministic_assignment_preparer,
        )
        improvement_coordinator = ImprovementCoordinator(
            improvement_coding,
            improvement_applier,
            evaluator,
            include_baseline_context=goal_driven_change_enabled,
        )
        if natural_change_enabled:
            if code_index is None:
                raise ValueError("Doğal dil değişiklik akışı güvenli kod indeksi gerektirir.")
            scope_resolver = SafeChangeScopeResolver(project_root, code_index)
            if goal_driven_change_enabled:
                if relationship_index is None:
                    raise ValueError("Hedef odaklı değişiklik akışı ilişki indeksi gerektirir.")
                scope_resolver = GoalDrivenChangeScopeResolver(
                    project_root,
                    code_index,
                    relationship_index,
                    impact_index,
                    batch_runtime_repair_enabled=batch_runtime_repair_enabled,
                )
            improvement_coordinator = NaturalLanguageImprovementCoordinator(
                improvement_coordinator,
                scope_resolver,
                runtime_repair_enabled=runtime_repair_enabled,
            )
        operation_resolvers.insert(0, improvement_coordinator)
    if external_tools_enabled:
        operation_resolvers.insert(
            0,
            DatabaseReadCoordinator(
                parser=RuleBasedDatabaseRequestParser(),
                service=ReadOnlySqliteService(project_root),
            ),
        )
        operation_resolvers.insert(
            0,
            ControlledApiCoordinator(
                parser=RuleBasedApiRequestParser(),
                policy=SafeApiPolicy(settings.api_allowed_hosts),
                client=BoundedHttpApiClient(),
            ),
        )
    if coding_operation is not None:
        operation_resolvers.insert(0, coding_operation)
    if web_research_enabled:
        from boru.web import WebResearchCoordinator
        operation_resolvers.insert(0, WebResearchCoordinator(chat_model))
    operation_coordinator = ExclusiveOperationCoordinator(operation_resolvers)

    performance_coordinator = (
        PerformanceStatusCoordinator(
            performance_monitor
        )
    )

    project_memory_coordinator = None
    project_memory_context_provider = None
    if project_memory_enabled:
        project_memory_service = ProjectMemoryService(
            repository=JsonProjectMemoryRepository(
                _resolve_path(settings.project_memory_path)
            ),
            project_name=project_root.name,
        )
        project_memory_coordinator = ProjectMemoryCoordinator(
            service=project_memory_service,
            parser=RuleBasedProjectMemoryParser(),
        )
        project_memory_context_provider = ProjectMemoryContextProvider(
            project_memory_service
        )

    knowledge_coordinator = None
    if knowledge_rag_enabled:
        knowledge_embedding_provider = None
        if settings.memory_semantic_enabled:
            knowledge_embedding_provider = OllamaEmbeddingProvider(
                settings.memory_embedding_model
            )
        knowledge_service = KnowledgeService(
            repository=JsonKnowledgeRepository(
                _resolve_path(settings.knowledge_path)
            ),
            loader=SafeKnowledgeDocumentLoader(
                ReadOnlyWorkspace(project_root, max_file_bytes=512 * 1024)
            ),
            chunker=TextKnowledgeChunker(),
            retriever=HybridKnowledgeRetriever(
                embedding_provider=knowledge_embedding_provider
            ),
        )
        knowledge_coordinator = KnowledgeCoordinator(
            service=knowledge_service,
            parser=RuleBasedKnowledgeRequestParser(),
            chat_model=chat_model,
        )

    conversation_model = chat_model
    if conversation_quality_enabled:
        from boru.conversation_quality import ConversationalChatModel, build_conversation_model
        conversation_model = build_conversation_model(
            settings.chat_model_name or settings.model_name,
            fallback_name='' if settings.chat_model_name else settings.fallback_model_name,
            performance_monitor=performance_monitor,
        )
        conversation_model = ConversationalChatModel(conversation_model)

    from boru.learning import (
        get_implicit_learner,
        get_reflection_learner,
        get_curiosity_daemon,
        get_dataset_collector,
        get_continuous_learning_engine,
    )
    implicit_learner = get_implicit_learner(project_root / "data" / "user_learned_profile.json")
    reflection_learner = get_reflection_learner(project_root / "data" / "reflection_rules.json")
    curiosity_daemon = get_curiosity_daemon(project_root / "data" / "curiosity_knowledge.json")
    dataset_collector = get_dataset_collector(project_root / "data" / "self_training_dataset.jsonl")
    continuous_learning_engine = get_continuous_learning_engine(project_root / "data")
    curiosity_daemon.start()
    continuous_learning_engine.start()

    assistant = (
        AssistantService(
            chat_model=(
                conversation_model
            ),
            conversation_history=(
                history
            ),
            prompt_factory=(
                SystemPromptFactory(
                    settings.assistant_name, conversational=conversation_quality_enabled
                )
            ),
            context_builder=(
                context_builder
            ),
            message_observers=[
                ProfileObserver(
                    profile_service
                ),
                MemoryObserver(
                    memory_service
                ),
            ],
            turn_observers=[
                implicit_learner,
                reflection_learner,
                dataset_collector,
                continuous_learning_engine,
            ],
            direct_response_resolvers=[
                *([SandboxCoordinator(sandbox_executor)] if sandbox_executor is not None else []),
                *([EvaluationCoordinator(evaluator)] if evaluator is not None else []),
                *([operation_coordinator] if runtime_repair_enabled else []),
                *([general_agent_coordinator] if general_agent_coordinator is not None else []),
                *(
                    [knowledge_coordinator]
                    if knowledge_coordinator is not None
                    else []
                ),
                *(
                    [project_memory_coordinator]
                    if project_memory_coordinator is not None
                    else []
                ),
                RuleBasedProfileQueryResolver(
                    profile_service
                ),
                memory_forget_resolver,
                RuleBasedMemoryQueryResolver(
                    memory_service
                ),
                performance_coordinator,
                architect_coordinator,
                *([] if runtime_repair_enabled else [operation_coordinator]),
                *([test_agent] if test_agent is not None else []),
                AutoTestGeneratorCoordinator(test_runner=(test_agent.resolve if test_agent is not None else None)),
                DependencyGraphCoordinator(project_root),
                *([security_agent] if security_agent is not None else []),
                *([code_review_agent] if code_review_agent is not None else []),
                command_coordinator,
                read_tool_coordinator,
                RelevantMemoryQueryResolver(
                    memory_service,
                    intent_detector=(
                        memory_intent_detector
                    ),
                ),
            ],
            context_providers=[
                SystemClockContextProvider(),
                AutonomousWebGroundingContextProvider(),
                *(
                    [project_memory_context_provider]
                    if project_memory_context_provider is not None
                    else []
                ),
                ProfileContextProvider(
                    profile_service
                ),
                MemoryContextProvider(
                    memory_service,
                    intent_detector=(
                        memory_intent_detector
                    ),
                ),
                implicit_learner,
                reflection_learner,
                continuous_learning_engine,
            ],
        )
    )

    application = ChatAppUI(
        assistant=assistant,
        title=f"Börü {application_version}",
        startup_message=(
            startup_message
            or (
                f"Börü {application_version} hazır. "
                "Canlı işlem süresi, model warmup/keep-alive, performans metrikleri ve "
                "değişiklik-duyarlı Architect önbelleği aktif."
            )
        ),
    )

    ModelWarmupService(
        chat_model,
        performance_monitor,
    ).start()

    return application


if __name__ == "__main__":
    application = (
        build_application()
    )

    application.mainloop()
