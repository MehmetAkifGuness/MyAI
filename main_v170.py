from pathlib import Path
import os

from boru.sandbox import DockerSandboxExecutor
from boru.sandbox.coordinator import SandboxCoordinator
from boru.evaluation import EvidenceEvaluator, EvaluationCoordinator
from boru.improvement import (
    ImprovementCoordinator,
    NaturalLanguageImprovementCoordinator,
    SafeChangeScopeResolver,
    VerifiedImprovementApplier,
)
from boru.agent import GeneralAgentCoordinator, ReadOnlyToolAgent
from boru.code_index import (
    CodeSearchTool,
    FileSymbolsTool,
    ProjectOverviewTool,
    RelatedCodeTool,
    SafeCodeIndex,
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
    RelatedTestDiscovery,
    RuleBasedTestAgentRequestParser,
    SafeTestAgent,
)
from boru.tasks import (
    ArchitectureTaskPlanner,
    RuleBasedTaskCommandParser,
    TaskPlanCoordinator,
)
from boru.ui import (
    ChatAppUI,
)


def _resolve_project_path(
    configured_path: str,
) -> Path:
    path = Path(
        configured_path
    )

    if path.is_absolute():
        return path

    return (
        Path(__file__)
        .resolve()
        .parent
        / path
    )


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
    project_edit_max_attempts: int = 2,
) -> ChatAppUI:
    if natural_change_enabled and not improvement_enabled:
        raise ValueError("Doğal dil değişiklik akışı kontrollü iyileştirme gerektirir.")

    settings = (
        AppSettings.from_env()
    )

    performance_monitor = (
        PerformanceMonitor()
    )

    chat_model = (
        OllamaChatModel(
            settings.model_name,
            request_timeout_seconds=180,
            structured_timeout_seconds=structured_timeout_seconds,
            structured_num_predict=structured_num_predict,
            keep_alive="10m",
            performance_monitor=(
                performance_monitor
            ),
        )
    )

    history = (
        ConversationHistory(
            max_turns=(
                settings.history_turns
            )
        )
    )

    context_builder = (
        ConversationContextBuilder(
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
                    _resolve_project_path(
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
        RuleBasedMemoryIntentDetector()
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
                    _resolve_project_path(
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

    project_root = (
        Path(__file__)
        .resolve()
        .parent
    )

    read_workspace = (
        ReadOnlyWorkspace(
            project_root
        )
    )

    code_index = None
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
            read_tools.append(
                RelatedCodeTool(SafeCodeRelationshipIndex(project_root))
            )

    read_registry = ToolRegistry(read_tools)

    read_executor = ToolExecutor(
        registry=read_registry,
        policy=RiskBasedToolPolicy(
            allowed_risks=(
                ToolRisk.SAFE,
                ToolRisk.READ_ONLY,
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
    if evaluation_enabled:
        if sandbox_executor is None:
            raise ValueError("Öz değerlendirme sandbox gerektirir.")
        evaluator = EvidenceEvaluator(project_root, command_executor)
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

    coding_coordinator = None
    if coding_agent_enabled:
        coding_coordinator = ControlledCodingCoordinator(
            parser=RuleBasedCodingRequestParser(
                architecture_request_parser
            ),
            architect=architect_agent,
            proposal_preparer=project_edit_preparer,
            proposal_applier=project_edit_applier,
            deterministic_edit_parser=RuleBasedSmartEditRequestParser(),
            deterministic_edit_preparer=deterministic_assignment_preparer,
            regression_runner=test_agent,
            security_reviewer=security_agent,
            code_reviewer=code_review_agent,
            quality_evaluator=evaluator,
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
        coding_operation = TaskPlanCoordinator(
            parser=RuleBasedTaskCommandParser(),
            planner=ArchitectureTaskPlanner(
                architect_agent,
                architecture_request_parser,
            ),
            workflow=agent_orchestrator,
        )

    operation_resolvers = [
        auto_fix_coordinator,
        controlled_write,
        git_coordinator,
    ]
    if improvement_enabled:
        if evaluator is None or coding_coordinator is None:
            raise ValueError("İyileştirme Coding, değerlendirme ve sandbox gerektirir.")
        def staged_evaluator(root):
            return EvidenceEvaluator(root, DockerSandboxExecutor(root, sandbox_image))

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
        )
        if natural_change_enabled:
            if code_index is None:
                raise ValueError("Doğal dil değişiklik akışı güvenli kod indeksi gerektirir.")
            improvement_coordinator = NaturalLanguageImprovementCoordinator(
                improvement_coordinator,
                SafeChangeScopeResolver(project_root, code_index),
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
                _resolve_project_path(settings.project_memory_path)
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
                _resolve_project_path(settings.knowledge_path)
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

    assistant = (
        AssistantService(
            chat_model=(
                chat_model
            ),
            conversation_history=(
                history
            ),
            prompt_factory=(
                SystemPromptFactory(
                    settings.assistant_name
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
            direct_response_resolvers=[
                *([SandboxCoordinator(sandbox_executor)] if sandbox_executor is not None else []),
                *([EvaluationCoordinator(evaluator)] if evaluator is not None else []),
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
                operation_coordinator,
                *([test_agent] if test_agent is not None else []),
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
