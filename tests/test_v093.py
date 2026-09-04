import tempfile
import unittest
from pathlib import Path

from boru.memory import (
    AliasAwareSubjectMatcher,
    ConservativeMemoryDecisionGate,
    DEFAULT_SUBJECT_ALIAS_GROUPS,
    ExplicitMemoryExtractor,
    GroundedMemoryDecisionEngine,
    JsonMemoryRepository,
    KeywordMemoryRetriever,
    LongTermMemoryService,
    RuleBasedMemoryForgetParser,
    RuleBasedMemoryStructurer,
    SubjectRelationConflictResolver,
)
from boru.memory.models import (
    MemoryDecision,
)


class AlwaysDifferentSubjectMatcher:
    def is_same_subject(
        self,
        left: str,
        right: str,
    ) -> bool:
        return False


class StaticDecisionEngine:
    def __init__(
        self,
        decision: MemoryDecision,
    ):
        self._decision = decision
        self.calls = 0

    def decide(
        self,
        user_message: str,
    ) -> MemoryDecision:
        self.calls += 1
        return self._decision


class V093MemorySafetyTests(
    unittest.TestCase
):
    def test_known_translation_alias_does_not_depend_on_embedding(
        self,
    ) -> None:
        matcher = AliasAwareSubjectMatcher(
            delegate=AlwaysDifferentSubjectMatcher(),
            alias_groups=(
                DEFAULT_SUBJECT_ALIAS_GROUPS
            ),
        )

        self.assertTrue(
            matcher.is_same_subject(
                "Calculator API",
                "Hesap makinesi API",
            )
        )

    def test_known_alias_does_not_merge_unrelated_subject(
        self,
    ) -> None:
        matcher = AliasAwareSubjectMatcher(
            delegate=AlwaysDifferentSubjectMatcher(),
            alias_groups=(
                DEFAULT_SUBJECT_ALIAS_GROUPS
            ),
        )

        self.assertFalse(
            matcher.is_same_subject(
                "Calculator API",
                "Auth API",
            )
        )

    def test_grounded_decision_rejects_invented_value(
        self,
    ) -> None:
        inner = StaticDecisionEngine(
            MemoryDecision(
                should_save=True,
                content=(
                    "yazılım geliştirme için "
                    "kullanılan teknoloji"
                ),
                subject="projeler",
                relation="backend_framework",
                value="react",
            )
        )

        engine = GroundedMemoryDecisionEngine(
            inner
        )

        decision = engine.decide(
            (
                "hesap makinesi api ile ilgili 2 "
                "uzun süreli hafıza kaydını unuttum."
            )
        )

        self.assertFalse(
            decision.should_save
        )

    def test_grounded_decision_allows_value_present_in_source(
        self,
    ) -> None:
        inner = StaticDecisionEngine(
            MemoryDecision(
                should_save=True,
                content=(
                    "Calculator API projem "
                    "FastAPI kullanıyor."
                ),
                subject="Calculator API",
                relation="backend_framework",
                value="FastAPI",
            )
        )

        engine = GroundedMemoryDecisionEngine(
            inner
        )

        decision = engine.decide(
            (
                "Calculator API projem "
                "FastAPI kullanıyor."
            )
        )

        self.assertTrue(
            decision.should_save
        )

        self.assertEqual(
            decision.value,
            "FastAPI",
        )

    def test_gate_rejects_memory_management_past_tense_statement(
        self,
    ) -> None:
        gate = ConservativeMemoryDecisionGate(
            forget_parser=(
                RuleBasedMemoryForgetParser()
            )
        )

        self.assertFalse(
            gate.should_evaluate(
                (
                    "hesap makinesi api ile ilgili 2 "
                    "uzun süreli hafıza kaydını unuttum."
                )
            )
        )

    def test_subject_forget_uses_deterministic_translation_alias(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            matcher = AliasAwareSubjectMatcher(
                delegate=(
                    AlwaysDifferentSubjectMatcher()
                ),
                alias_groups=(
                    DEFAULT_SUBJECT_ALIAS_GROUPS
                ),
            )

            service = LongTermMemoryService(
                repository=(
                    JsonMemoryRepository(
                        Path(directory)
                        / "memory.json"
                    )
                ),
                extractor=(
                    ExplicitMemoryExtractor()
                ),
                retriever=(
                    KeywordMemoryRetriever()
                ),
                structurer=(
                    RuleBasedMemoryStructurer()
                ),
                conflict_resolver=(
                    SubjectRelationConflictResolver(
                        subject_matcher=matcher
                    )
                ),
                subject_matcher=matcher,
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "pytest kullanıyor."
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Calculator API projem "
                    "FastAPI kullanıyor."
                )
            )

            service.observe(
                (
                    "Bunu hatırla: "
                    "Auth API projem "
                    "unittest kullanıyor."
                )
            )

            removed = service.forget_subject(
                "hesap makinesi API"
            )

            self.assertEqual(
                len(removed),
                2,
            )

            remaining = service.list_recent()

            self.assertEqual(
                len(remaining),
                1,
            )

            self.assertEqual(
                remaining[0].subject,
                "Auth API",
            )

    def test_grounded_engine_prevents_hallucinated_auto_memory_from_service(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inner = StaticDecisionEngine(
                MemoryDecision(
                    should_save=True,
                    content=(
                        "yazılım geliştirme için "
                        "kullanılan teknoloji"
                    ),
                    subject="projeler",
                    relation="backend_framework",
                    value="react",
                )
            )

            service = LongTermMemoryService(
                repository=(
                    JsonMemoryRepository(
                        Path(directory)
                        / "memory.json"
                    )
                ),
                extractor=(
                    ExplicitMemoryExtractor()
                ),
                retriever=(
                    KeywordMemoryRetriever()
                ),
                decision_engine=(
                    GroundedMemoryDecisionEngine(
                        inner
                    )
                ),
                decision_gate=(
                    ConservativeMemoryDecisionGate()
                ),
            )

            changed = service.observe(
                (
                    "Calculator API projem artık "
                    "FastAPI kullanıyor."
                )
            )

            self.assertEqual(
                changed,
                [],
            )

            self.assertEqual(
                service.list_recent(),
                [],
            )


if __name__ == "__main__":
    unittest.main()