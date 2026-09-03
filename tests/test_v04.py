import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.assistant import (
    AssistantService,
)
from boru.conversation import (
    ConversationHistory,
)
from boru.memory import (
    ExplicitMemoryExtractor,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LongTermMemoryService,
    MemoryContextProvider,
    MemoryObserver,
    RuleBasedMemoryQueryResolver,
)
from boru.models import (
    ChatMessage,
)
from boru.prompts import (
    SystemPromptFactory,
)


class RecordingChatModel:
    def __init__(
        self,
        response: str = "LLM cevabı",
    ):
        self.response = response

        self.calls: list[
            list[ChatMessage]
        ] = []

    def generate(
        self,
        messages: Sequence[
            ChatMessage
        ],
    ) -> str:
        self.calls.append(
            list(messages)
        )

        return self.response


class LongTermMemoryTests(
    unittest.TestCase
):
    @staticmethod
    def _create_service(
        path: Path,
    ) -> LongTermMemoryService:
        return LongTermMemoryService(
            repository=(
                JsonMemoryRepository(
                    path
                )
            ),
            extractor=(
                ExplicitMemoryExtractor()
            ),
            retriever=(
                KeywordMemoryRetriever()
            ),
            context_limit=5,
        )

    def test_explicit_memory_persists_across_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "calculator API projem "
                    "pytest kullanıyor."
                )
            )

            restarted = (
                self._create_service(
                    path
                )
            )

            memories = (
                restarted.list_recent()
            )

            self.assertEqual(
                len(memories),
                1,
            )

            self.assertEqual(
                memories[0].content,
                (
                    "calculator API projem "
                    "pytest kullanıyor."
                ),
            )

    def test_normal_message_is_not_persisted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            saved = service.observe(
                (
                    "Bugün Python "
                    "çalışıyorum."
                )
            )

            self.assertEqual(
                saved,
                [],
            )

            self.assertFalse(
                path.exists()
            )

    def test_duplicate_memory_is_not_saved_twice(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "FastAPI kullanıyorum."
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "fastapi kullanıyorum."
                )
            )

            self.assertEqual(
                len(
                    service.list_recent()
                ),
                1,
            )

    def test_relevant_memory_is_added_to_model_context(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "calculator API projem "
                    "pytest kullanıyor."
                )
            )

            model = RecordingChatModel(
                (
                    "Pytest "
                    "kullanıyorsun."
                )
            )

            assistant = (
                AssistantService(
                    chat_model=model,
                    conversation_history=(
                        ConversationHistory()
                    ),
                    prompt_factory=(
                        SystemPromptFactory(
                            "Börü"
                        )
                    ),
                    message_observers=[
                        MemoryObserver(
                            service
                        )
                    ],
                    context_providers=[
                        MemoryContextProvider(
                            service
                        )
                    ],
                )
            )

            assistant.reply(
                (
                    "Calculator API projem "
                    "ne kullanıyor?"
                )
            )

            system_messages = [
                message.content
                for message
                in model.calls[0]
                if (
                    message.role
                    == "system"
                )
            ]

            self.assertTrue(
                any(
                    (
                        "pytest"
                        in message.casefold()
                    )
                    for message
                    in system_messages
                )
            )

    def test_memory_list_query_bypasses_llm(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            service = (
                self._create_service(
                    path
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Projede FastAPI "
                    "kullanıyorum."
                )
            )

            model = (
                RecordingChatModel()
            )

            resolver = (
                RuleBasedMemoryQueryResolver(
                    service
                )
            )

            assistant = (
                AssistantService(
                    chat_model=model,
                    conversation_history=(
                        ConversationHistory()
                    ),
                    prompt_factory=(
                        SystemPromptFactory(
                            "Börü"
                        )
                    ),
                    direct_response_resolvers=[
                        resolver
                    ],
                )
            )

            answer = assistant.reply(
                "Hafızanda ne var?"
            )

            self.assertIn(
                "FastAPI",
                answer,
            )

            self.assertEqual(
                model.calls,
                [],
            )


if __name__ == "__main__":
    unittest.main()