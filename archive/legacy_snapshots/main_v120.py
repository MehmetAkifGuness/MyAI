from pathlib import Path

from boru.assistant import (
    AssistantService,
)
from boru.config import (
    AppSettings,
)
from boru.context import (
    ConversationContextBuilder,
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
from boru.ollama_model import (
    OllamaChatModel,
)
from boru.profile import (
    JsonUserProfileRepository,
    ProfileContextProvider,
    ProfileObserver,
    RuleBasedProfileExtractor,
    RuleBasedProfileQueryResolver,
    UserProfileService,
)
from boru.prompts import (
    SystemPromptFactory,
)
from boru.tools import (
    CalculatorTool,
    ChainedToolPlanner,
    CompositeToolResultSynthesizer,
    ControlledWriteCoordinator,
    CurrentTimeTool,
    DirectoryCountSynthesisResolver,
    EditFileTool,
    FallbackSmartEditProposalPreparer,
    FallbackToolPlanner,
    GroundedLLMToolResultSynthesizer,
    LLMToolPlanner,
    LLMProjectEditProposalPreparer,
    LLMProjectFileSelector,
    LLMSmartEditProposalPreparer,
    ListDirectoryTool,
    NaturalLanguageToolPlanner,
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    RuleBasedProjectEditRequestParser,
    RuleBasedAssignmentEditProposalPreparer,
    RuleBasedEditRequestParser,
    RuleBasedSmartEditRequestParser,
    RuleBasedToolCandidateDetector,
    RuleBasedToolPlanner,
    RuleBasedWriteIntentDetector,
    RuleBasedWriteRequestParser,
    SafeEditWorkspace,
    SafeProjectFileIndex,
    SafeWriteWorkspace,
    BatchProjectEditApplier,
    ToolCoordinator,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
    WriteFileTool,
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
) -> ChatAppUI:
    settings = (
        AppSettings.from_env()
    )

    chat_model = (
        OllamaChatModel(
            settings.model_name
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

    read_registry = ToolRegistry(
        [
            CalculatorTool(),
            CurrentTimeTool(),
            ListDirectoryTool(
                read_workspace
            ),
            ReadFileTool(
                read_workspace
            ),
        ]
    )

    read_executor = ToolExecutor(
        registry=read_registry,
        policy=RiskBasedToolPolicy(
            allowed_risks=(
                ToolRisk.SAFE,
                ToolRisk.READ_ONLY,
            )
        ),
    )

    read_planner = FallbackToolPlanner(
        primary=ChainedToolPlanner(
            [
                RuleBasedToolPlanner(),
                NaturalLanguageToolPlanner(),
            ]
        ),
        fallback=LLMToolPlanner(
            chat_model=chat_model,
            registry=read_registry,
        ),
        candidate_detector=(
            RuleBasedToolCandidateDetector()
        ),
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

    smart_edit_preparer = (
        FallbackSmartEditProposalPreparer(
            primary=(
                RuleBasedAssignmentEditProposalPreparer(
                    workspace=edit_workspace
                )
            ),
            fallback=(
                LLMSmartEditProposalPreparer(
                    chat_model=chat_model,
                    workspace=edit_workspace,
                    max_attempts=2,
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

    project_file_selector = (
        LLMProjectFileSelector(
            chat_model=chat_model,
            max_files=4,
            max_attempts=2,
        )
    )

    project_edit_preparer = (
        LLMProjectEditProposalPreparer(
            chat_model=chat_model,
            file_index=project_file_index,
            file_selector=project_file_selector,
            workspace=edit_workspace,
            max_files=4,
            max_attempts=2,
        )
    )

    project_edit_applier = (
        BatchProjectEditApplier(
            workspace=edit_workspace
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
            executor=write_executor,
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
        )
    )

    assistant = (
        AssistantService(
            chat_model=chat_model,
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
                RuleBasedProfileQueryResolver(
                    profile_service
                ),
                memory_forget_resolver,
                RuleBasedMemoryQueryResolver(
                    memory_service
                ),
                controlled_write,
                read_tool_coordinator,
                RelevantMemoryQueryResolver(
                    memory_service,
                    intent_detector=(
                        memory_intent_detector
                    ),
                ),
            ],
            context_providers=[
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

    return ChatAppUI(
        assistant=assistant,
        title="Börü V0.12.0",
        startup_message=(
            "Börü V0.12.0 hazır. "
            "Mevcut güvenli tool, hafıza ve kontrollü write/edit altyapısına ek olarak "
            "güvenli project file index, manifest-kısıtlı ilgili dosya seçimi, "
            "grounded multi-file patch planlama, toplu diff önizleme ve "
            "tek onaylı rollback destekli project-aware düzenleme aktif."
        ),
    )


if __name__ == "__main__":
    application = (
        build_application()
    )

    application.mainloop()