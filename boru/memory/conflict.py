from collections.abc import Sequence

from boru.memory.contracts import (
    MemorySubjectMatcher,
)
from boru.memory.models import (
    MemoryRecord,
    StructuredMemoryFact,
)
from boru.memory.subject_matcher import (
    ExactSubjectMatcher,
)


class SubjectRelationConflictResolver:
    """
    Aynı relation'a ve aynı gerçek subject
    kimliğine sahip yapılandırılmış hafıza
    kaydını bulur.

    Varsayılan matcher exact eşleşmedir;
    semantic matcher dependency injection ile
    verildiğinde paraphrase subject'leri de
    aynı kimlik olarak değerlendirebilir.
    """

    def __init__(
        self,
        subject_matcher: (
            MemorySubjectMatcher | None
        ) = None,
    ):
        self._subject_matcher = (
            subject_matcher
            or ExactSubjectMatcher()
        )

    def find_existing(
        self,
        fact: StructuredMemoryFact,
        memories: Sequence[MemoryRecord],
    ) -> MemoryRecord | None:
        relation_key = self._normalize(
            fact.relation
        )

        for memory in memories:
            existing_fact = (
                memory.fact
            )

            if existing_fact is None:
                continue

            if (
                self._normalize(
                    existing_fact.relation
                )
                != relation_key
            ):
                continue

            if (
                self._subject_matcher
                .is_same_subject(
                    existing_fact.subject,
                    fact.subject,
                )
            ):
                return memory

        return None

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:
        return " ".join(
            value
            .casefold()
            .strip()
            .split()
        )