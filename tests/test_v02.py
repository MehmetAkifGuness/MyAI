import unittest

from boru.context import (
    ConversationContextBuilder,
)
from boru.models import ChatMessage


class ConversationContextBuilderTests(
    unittest.TestCase
):
    def test_context_respects_max_turns(
        self,
    ):
        builder = (
            ConversationContextBuilder(
                max_turns=2,
                max_characters=10_000,
            )
        )

        history = [
            ChatMessage("user", "u1"),
            ChatMessage("assistant", "a1"),
            ChatMessage("user", "u2"),
            ChatMessage("assistant", "a2"),
            ChatMessage("user", "u3"),
            ChatMessage("assistant", "a3"),
        ]

        context = builder.build(history)

        self.assertEqual(
            context,
            [
                ChatMessage("user", "u2"),
                ChatMessage(
                    "assistant",
                    "a2",
                ),
                ChatMessage("user", "u3"),
                ChatMessage(
                    "assistant",
                    "a3",
                ),
            ],
        )

    def test_context_respects_character_limit(
        self,
    ):
        builder = (
            ConversationContextBuilder(
                max_turns=10,
                max_characters=12,
            )
        )

        history = [
            ChatMessage(
                "user",
                "aaaaa",
            ),
            ChatMessage(
                "assistant",
                "bbbbb",
            ),
            ChatMessage(
                "user",
                "ccccc",
            ),
            ChatMessage(
                "assistant",
                "ddddd",
            ),
        ]

        context = builder.build(history)

        self.assertEqual(
            context,
            [
                ChatMessage(
                    "user",
                    "ccccc",
                ),
                ChatMessage(
                    "assistant",
                    "ddddd",
                ),
            ],
        )

    def test_latest_turn_is_kept_even_if_large(
        self,
    ):
        builder = (
            ConversationContextBuilder(
                max_turns=10,
                max_characters=5,
            )
        )

        history = [
            ChatMessage(
                "user",
                "çok uzun kullanıcı mesajı",
            ),
            ChatMessage(
                "assistant",
                "çok uzun cevap",
            ),
        ]

        context = builder.build(history)

        self.assertEqual(
            context,
            history,
        )

    def test_empty_history_returns_empty_context(
        self,
    ):
        builder = (
            ConversationContextBuilder()
        )

        self.assertEqual(
            builder.build([]),
            [],
        )

    def test_incomplete_turn_is_rejected(
        self,
    ):
        builder = (
            ConversationContextBuilder()
        )

        history = [
            ChatMessage(
                "user",
                "Merhaba",
            )
        ]

        with self.assertRaises(
            ValueError
        ):
            builder.build(history)


if __name__ == "__main__":
    unittest.main()