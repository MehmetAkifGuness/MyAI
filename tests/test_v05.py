import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.memory import (
    ConservativeMemoryDecisionGate,
    ExplicitMemoryExtractor,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LLMMemoryDecisionEngine,
    LongTermMemoryService,
)
from boru.memory.models import (
    MemoryDecision,
)
from boru.models import (
    ChatMessage,
)


class RecordingChatModel:
    def __init__(
        self,
        response: str,
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


class FixedDecisionEngine:
    def __init__(
        self,
        decision: MemoryDecision,
    ):
        self.decision = decision
        self.calls: list[str] = []

    def decide(
        self,
        user_message: str,
    ) -> MemoryDecision:
        self.calls.append(
            user_message
        )

        return self.decision


class AlwaysGate:
    def should_evaluate(
        self,
        user_message: str,
    ) -> bool:
        return True


class AutoMemoryDecisionTests(
    unittest.TestCase
):
    def test_gate_rejects_question(
        self,
    ) -> None:
        gate = (
            ConservativeMemoryDecisionGate()
        )

        self.assertFalse(
            gate.should_evaluate(
                (
                    "Calculator API projem "
                    "ne kullanıyor?"
                )
            )
        )

    def test_gate_rejects_transient_statement(
        self,
    ) -> None:
        gate = (
            ConservativeMemoryDecisionGate()
        )

        self.assertFalse(
            gate.should_evaluate(
                (
                    "Bugün Python "
                    "çalışıyorum ve "
                    "test yazıyorum."
                )
            )
        )

    def test_gate_rejects_profile_statement(
        self,
    ) -> None:
        gate = (
            ConservativeMemoryDecisionGate()
        )

        self.assertFalse(
            gate.should_evaluate(
                (
                    "Benim favori "
                    "rengim mavi."
                )
            )
        )

    def test_gate_allows_stable_project_statement(
        self,
    ) -> None:
        gate = (
            ConservativeMemoryDecisionGate()
        )

        self.assertTrue(
            gate.should_evaluate(
                (
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )
        )

    def test_llm_decision_engine_parses_valid_json(
        self,
    ) -> None:
        model = RecordingChatModel(
            (
                '{"save": true, '
                '"content": '
                '"Calculator API projem '
                'pytest kullanıyor.", '
                '"reason": '
                '"Kalıcı proje bilgisi."}'
            )
        )

        engine = (
            LLMMemoryDecisionEngine(
                model
            )
        )

        decision = engine.decide(
            (
                "Calculator API projem "
                "pytest kullanıyor."
            )
        )

        self.assertTrue(
            decision.should_save
        )

        self.assertEqual(
            decision.content,
            (
                "Calculator API projem "
                "pytest kullanıyor."
            ),
        )

        self.assertEqual(
            len(model.calls),
            1,
        )

    def test_llm_decision_engine_fails_closed_on_invalid_output(
        self,
    ) -> None:
        engine = (
            LLMMemoryDecisionEngine(
                RecordingChatModel(
                    "bunu kaydet bence"
                )
            )
        )

        decision = engine.decide(
            (
                "Calculator API projem "
                "pytest kullanıyor."
            )
        )

        self.assertFalse(
            decision.should_save
        )

        self.assertIsNone(
            decision.content
        )

    def test_service_auto_saves_approved_candidate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            engine = (
                FixedDecisionEngine(
                    MemoryDecision(
                        should_save=True,
                        content=(
                            "Calculator API "
                            "projem pytest "
                            "kullanıyor."
                        ),
                        reason=(
                            "Kalıcı proje "
                            "bilgisi."
                        ),
                    )
                )
            )

            service = (
                LongTermMemoryService(
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
                    decision_engine=(
                        engine
                    ),
                    decision_gate=(
                        AlwaysGate()
                    ),
                )
            )

            saved = service.observe(
                (
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            self.assertEqual(
                len(saved),
                1,
            )

            self.assertEqual(
                saved[0].content,
                (
                    "Calculator API projem "
                    "pytest kullanıyor."
                ),
            )

            self.assertTrue(
                path.exists()
            )

    def test_explicit_memory_does_not_call_decision_engine(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "memory.json"
            )

            engine = (
                FixedDecisionEngine(
                    MemoryDecision(
                        should_save=False,
                        reason=(
                            "Kaydetme."
                        ),
                    )
                )
            )

            service = (
                LongTermMemoryService(
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
                    decision_engine=(
                        engine
                    ),
                    decision_gate=(
                        AlwaysGate()
                    ),
                )
            )

            saved = service.observe(
                (
                    "Bunu hatırla: "
                    "Projede FastAPI "
                    "kullanıyorum."
                )
            )

            self.assertEqual(
                len(saved),
                1,
            )

            self.assertEqual(
                engine.calls,
                [],
            )


if __name__ == "__main__":
    unittest.main()