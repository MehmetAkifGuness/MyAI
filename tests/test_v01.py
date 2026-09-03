import unittest
from collections.abc import Sequence

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory


class RecordingChatModel:
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)
        self.calls: list[list[ChatMessage]] = []

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        return next(self._responses)


class AssistantServiceTests(unittest.TestCase):
    def test_second_message_contains_previous_turn(self):
        model = RecordingChatModel(
            [
                "Selam!",
                "Daha önce selam verdin.",
            ]
        )

        assistant = AssistantService(
            chat_model=model,
            conversation_history=ConversationHistory(max_turns=10),
            prompt_factory=SystemPromptFactory("Börü"),
        )

        assistant.reply("selam")
        assistant.reply("Az önce ne dedim?")

        second_call = model.calls[1]

        self.assertEqual(
            second_call[0].role,
            "system",
        )

        self.assertEqual(
            second_call[1],
            ChatMessage(
                role="user",
                content="selam",
            ),
        )

        self.assertEqual(
            second_call[2],
            ChatMessage(
                role="assistant",
                content="Selam!",
            ),
        )

        self.assertEqual(
            second_call[3],
            ChatMessage(
                role="user",
                content="Az önce ne dedim?",
            ),
        )

    def test_history_keeps_only_configured_turn_count(self):
        history = ConversationHistory(max_turns=2)

        history.add_turn("u1", "a1")
        history.add_turn("u2", "a2")
        history.add_turn("u3", "a3")

        self.assertEqual(
            history.snapshot(),
            [
                ChatMessage(
                    role="user",
                    content="u2",
                ),
                ChatMessage(
                    role="assistant",
                    content="a2",
                ),
                ChatMessage(
                    role="user",
                    content="u3",
                ),
                ChatMessage(
                    role="assistant",
                    content="a3",
                ),
            ],
        )

    def test_failed_generation_is_not_written_to_history(self):
        model = RecordingChatModel(["   "])

        history = ConversationHistory(
            max_turns=10,
        )

        assistant = AssistantService(
            chat_model=model,
            conversation_history=history,
            prompt_factory=SystemPromptFactory("Börü"),
        )

        with self.assertRaises(RuntimeError):
            assistant.reply("Merhaba")

        self.assertEqual(
            history.snapshot(),
            [],
        )

    def test_reset_clears_conversation(self):
        model = RecordingChatModel(
            ["Merhaba!"]
        )

        history = ConversationHistory(
            max_turns=10,
        )

        assistant = AssistantService(
            chat_model=model,
            conversation_history=history,
            prompt_factory=SystemPromptFactory("Börü"),
        )

        assistant.reply("Merhaba")

        assistant.reset_conversation()

        self.assertEqual(
            history.snapshot(),
            [],
        )

    def test_empty_user_message_is_rejected(self):
        assistant = AssistantService(
            chat_model=RecordingChatModel(["unused"]),
            conversation_history=ConversationHistory(max_turns=10),
            prompt_factory=SystemPromptFactory("Börü"),
        )

        with self.assertRaises(ValueError):
            assistant.reply("   ")


if __name__ == "__main__":
    unittest.main()