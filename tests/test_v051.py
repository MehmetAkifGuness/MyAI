import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.memory import (
    ExplicitMemoryExtractor,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LongTermMemoryService,
    RelevantMemoryQueryResolver,
)
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory


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
        messages: Sequence[ChatMessage],
    ) -> str:
        self.calls.append(
            list(messages)
        )

        return self.response


class RelevantMemoryQueryTests(
    unittest.TestCase
):
    @staticmethod
    def _create_service(
        path: Path,
    ) -> LongTermMemoryService:
        return LongTermMemoryService(
            repository=JsonMemoryRepository(
                path
            ),
            extractor=ExplicitMemoryExtractor(),
            retriever=KeywordMemoryRetriever(),
        )

    def test_relevant_question_returns_memory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._create_service(
                Path(directory)
                / "memory.json"
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            resolver = RelevantMemoryQueryResolver(
                service
            )

            self.assertEqual(
                resolver.resolve(
                    (
                        "Calculator API projem "
                        "ne kullanıyor?"
                    )
                ),
                (
                    "Hafızamdaki ilgili bilgiye göre: "
                    "Calculator API projem pytest kullanıyor."
                ),
            )

    def test_normal_statement_is_not_handled(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._create_service(
                Path(directory)
                / "memory.json"
            )

            resolver = RelevantMemoryQueryResolver(
                service
            )

            self.assertIsNone(
                resolver.resolve(
                    "Bugün Java çalışıyorum."
                )
            )

    def test_general_question_without_memory_intent_is_not_handled(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._create_service(
                Path(directory)
                / "memory.json"
            )

            resolver = RelevantMemoryQueryResolver(
                service
            )

            self.assertIsNone(
                resolver.resolve(
                    "Python nedir?"
                )
            )

    def test_relevant_memory_query_bypasses_llm(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self._create_service(
                Path(directory)
                / "memory.json"
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            model = RecordingChatModel()

            assistant = AssistantService(
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
                    RelevantMemoryQueryResolver(
                        service
                    )
                ],
            )

            answer = assistant.reply(
                (
                    "Calculator API projem "
                    "ne kullanıyor?"
                )
            )

            self.assertEqual(
                answer,
                (
                    "Hafızamdaki ilgili bilgiye göre: "
                    "Calculator API projem pytest kullanıyor."
                ),
            )

            self.assertEqual(
                model.calls,
                [],
            )


if __name__ == "__main__":
    unittest.main()