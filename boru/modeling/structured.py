from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from boru.models import ChatMessage


T = TypeVar("T")


def structured_model_for_attempt(model, attempt: int):
    selector = getattr(type(model), "model_for_attempt", None)
    return selector(model, attempt) if callable(selector) else model


@dataclass(frozen=True, slots=True)
class StructuredGeneration(Generic[T]):
    value: T
    raw: str
    attempts: int
    errors: tuple[str, ...]
    output_characters: int


class StructuredGenerationError(ValueError):
    def __init__(self, kind: str, attempts: int, errors: tuple[str, ...], output_characters: int):
        super().__init__(f"Structured çıktı {attempts} denemede doğrulanamadı: {errors[-1]}")
        self.kind = kind
        self.attempts = attempts
        self.errors = errors
        self.output_characters = output_characters


@dataclass(frozen=True, slots=True)
class StructuredModelCascade:
    """Uses a fast primary model and a fallback for structured retries."""

    primary: Any
    fallback: Any

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        return self.primary.generate(messages)

    def generate_structured(
        self, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> str:
        return self.primary.generate_structured(messages, schema)

    def model_for_attempt(self, attempt: int):
        return self.primary if attempt == 1 else self.fallback

    def warmup(self) -> None:
        warmup = getattr(self.primary, "warmup", None)
        if callable(warmup):
            warmup()


class ValidatedStructuredGenerator:
    """Retries bounded structured calls with exact validation feedback."""

    def __init__(self, *, max_attempts: int = 2, feedback_characters: int = 4000):
        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("Structured deneme sınırı 1 ile 3 arasında olmalıdır.")
        if feedback_characters < 256 or feedback_characters > 16000:
            raise ValueError("Structured geri bildirim sınırı 256-16000 olmalıdır.")
        self._max_attempts = max_attempts
        self._feedback_characters = feedback_characters

    def generate(
        self,
        model,
        messages: Sequence[ChatMessage],
        schema: Mapping[str, Any],
        validator: Callable[[str], T],
    ) -> StructuredGeneration[T]:
        current = list(messages)
        errors: list[str] = []
        output_characters = 0
        last_kind = "validation"
        for attempt in range(1, self._max_attempts + 1):
            raw = ""
            try:
                attempt_model = structured_model_for_attempt(model, attempt)
                raw = attempt_model.generate_structured(current, schema)
                output_characters += len(raw) if isinstance(raw, str) else 0
            except Exception as error:
                # A provider failure is an outcome at this bounded model boundary.
                last_kind = "model"
                errors.append(str(error)[:500])
                if attempt >= self._max_attempts:
                    break
                current.append(ChatMessage(
                    role="user",
                    content="Model çağrısı tamamlanamadı. Aynı structured isteği bir kez daha dene.",
                ))
                continue
            try:
                value = validator(raw)
                return StructuredGeneration(value, raw, attempt, tuple(errors), output_characters)
            except Exception as error:
                # Parser/schema validation failures are safe to feed back to the same model.
                last_kind = "validation"
                errors.append(str(error)[:500])
                if attempt >= self._max_attempts:
                    break
                current.append(ChatMessage(
                    role="user",
                    content=(
                        "Önceki structured çıktı doğrulanamadı. Aynı görevi yalnızca şemaya uyan JSON ile "
                        "yeniden üret.\nVALIDATION_ERROR:\n" + str(error)[:1000]
                        + "\nINVALID_OUTPUT:\n" + str(raw)[: self._feedback_characters]
                    ),
                ))
        raise StructuredGenerationError(
            last_kind, self._max_attempts, tuple(errors), output_characters
        )
