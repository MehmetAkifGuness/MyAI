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
    ConservativeMemoryDecisionGate,
    ExplicitMemoryExtractor,
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
            ExactSubjectMatcher()
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

    conflict_resolver = (
        SubjectRelationConflictResolver(
            subject_matcher=(
                semantic_subject_matcher
            )
        )
    )

    return (
        hybrid_retriever,
        conflict_resolver,
        semantic_subject_matcher,
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
            LLMMemoryDecisionEngine(
                chat_model
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
        title="Börü V0.9.2",
        startup_message=(
            "Börü V0.9.2 hazır. "
            "Güvenli semantic hafıza kimliği, relation bazlı "
            "unutma, subject-level unutma ve iki "
            "aşamalı toplu silme aktif."
        ),
    )


if __name__ == "__main__":
    application = (
        build_application()
    )

    application.mainloop()