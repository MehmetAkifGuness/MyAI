from collections.abc import Sequence

from boru.models import ChatMessage


class ConversationContextBuilder:
    """
    Kısa süreli konuşma geçmişinden modele gönderilecek
    context penceresini oluşturur.
    """

    MESSAGES_PER_TURN = 2

    def __init__(
        self,
        max_turns: int = 10,
        max_characters: int = 12_000,
    ):
        if max_turns < 1:
            raise ValueError("max_turns en az 1 olmalıdır.")

        if max_characters < 1:
            raise ValueError(
                "max_characters en az 1 olmalıdır."
            )

        self._max_turns = max_turns
        self._max_characters = max_characters

    def build(
        self,
        history: Sequence[ChatMessage],
    ) -> list[ChatMessage]:
        messages = list(history)

        if not messages:
            return []

        if len(messages) % self.MESSAGES_PER_TURN != 0:
            raise ValueError(
                "Konuşma geçmişi tamamlanmış "
                "user/assistant turlarından oluşmalıdır."
            )

        max_message_count = (
            self._max_turns
            * self.MESSAGES_PER_TURN
        )

        candidates = messages[-max_message_count:]

        selected_turns: list[list[ChatMessage]] = []
        used_characters = 0

        for index in range(
            len(candidates) - self.MESSAGES_PER_TURN,
            -1,
            -self.MESSAGES_PER_TURN,
        ):
            turn = candidates[
                index:index + self.MESSAGES_PER_TURN
            ]

            turn_character_count = sum(
                len(message.content)
                for message in turn
            )

            if (
                selected_turns
                and used_characters + turn_character_count
                > self._max_characters
            ):
                break

            selected_turns.append(turn)
            used_characters += turn_character_count

            if used_characters >= self._max_characters:
                break

        selected_turns.reverse()

        return [
            message
            for turn in selected_turns
            for message in turn
        ]