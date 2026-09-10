import unittest
from collections.abc import Sequence

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory


class MockStreamingModel:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks
        self.generate_called = False
        self.stream_called = False

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        self.generate_called = True
        return "".join(self._chunks)

    def generate_stream(self, messages: Sequence[ChatMessage]):
        self.stream_called = True
        for chunk in self._chunks:
            yield chunk


class MockNonStreamingModel:
    def __init__(self, answer: str):
        self._answer = answer

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        return self._answer


class StreamingAssistantTests(unittest.TestCase):
    def test_reply_stream_yields_tokens_and_records_history(self):
        chunks = ["Merhaba", " dünya", "!"]
        model = MockStreamingModel(chunks)
        history = ConversationHistory(max_turns=5)
        assistant = AssistantService(
            chat_model=model,
            conversation_history=history,
            prompt_factory=SystemPromptFactory("Börü"),
        )

        stream_gen = assistant.reply_stream("Selam")
        received = list(stream_gen)

        self.assertEqual(received, chunks)
        self.assertTrue(model.stream_called)
        self.assertFalse(model.generate_called)

        snapshot = history.snapshot()
        self.assertEqual(len(snapshot), 2)
        self.assertEqual(snapshot[0].role, "user")
        self.assertEqual(snapshot[0].content, "Selam")
        self.assertEqual(snapshot[1].role, "assistant")
        self.assertEqual(snapshot[1].content, "Merhaba dünya!")

    def test_reply_stream_falls_back_when_model_has_no_stream(self):
        model = MockNonStreamingModel("Tek parça yanıt.")
        history = ConversationHistory(max_turns=5)
        assistant = AssistantService(
            chat_model=model,
            conversation_history=history,
            prompt_factory=SystemPromptFactory("Börü"),
        )

        stream_gen = assistant.reply_stream("Nasılsın?")
        received = list(stream_gen)

        self.assertEqual(received, ["Tek parça yanıt."])
        self.assertEqual(len(history.snapshot()), 2)
        self.assertEqual(history.snapshot()[1].content, "Tek parça yanıt.")


if __name__ == "__main__":
    unittest.main()
