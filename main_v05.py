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
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LLMMemoryDecisionEngine,
    LongTermMemoryService,
    MemoryContextProvider,
    MemoryObserver,
    RuleBasedMemoryQueryResolver,
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

    project_root = (
        Path(__file__)
        .resolve()
        .parent
    )

    return (
        project_root
        / path
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

    memory_decision_engine = None
    memory_decision_gate = None

    if settings.memory_auto_capture:
        memory_decision_engine = (
            LLMMemoryDecisionEngine(
                chat_model
            )
        )

        memory_decision_gate = (
            ConservativeMemoryDecisionGate()
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
                KeywordMemoryRetriever()
            ),
            context_limit=(
                settings.memory_context_limit
            ),
            decision_engine=(
                memory_decision_engine
            ),
            decision_gate=(
                memory_decision_gate
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
                RuleBasedMemoryQueryResolver(
                    memory_service
                ),
            ],
            context_providers=[
                ProfileContextProvider(
                    profile_service
                ),
                MemoryContextProvider(
                    memory_service
                ),
            ],
        )
    )

    return ChatAppUI(
        assistant=assistant,
        title="Börü V0.5",
        startup_message=(
            "Börü V0.5 hazır. "
            "Kısa süreli context, "
            "kalıcı profil, uzun süreli "
            "hafıza ve kontrollü otomatik "
            "hafıza kararı aktif."
        ),
    )


if __name__ == "__main__":
    application = (
        build_application()
    )

    application.mainloop()