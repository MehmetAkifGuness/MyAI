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
        max_turn_characters: int | None = None,
    ):
        if max_turns < 1:
            raise ValueError("max_turns en az 1 olmalıdır.")

        if max_characters < 1:
            raise ValueError(
                "max_characters en az 1 olmalıdır."
            )

        self._max_turns = max_turns
        self._max_characters = max_characters
        if max_turn_characters is not None and max_turn_characters < 1:
            raise ValueError('max_turn_characters pozitif olmalıdır.')
        self._max_turn_characters = max_turn_characters

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
            if self._max_turn_characters is not None:
                cap = min(self._max_turn_characters, max(2, self._max_characters // 2))
                turn = self._bounded_turn(turn, cap)

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

    @staticmethod
    def _bounded_turn(turn, cap):
        if sum(len(m.content) for m in turn) <= cap:
            return turn
        result = []
        for message in turn:
            limit = cap // 2
            content = message.content
            if len(content) > limit:
                marker = '\n[bağlam kısaltıldı]\n'
                space = max(0, limit - len(marker))
                content = content[:space // 2] + marker + (content[-(space - space // 2):] if space else '')
        return result


class SystemClockContextProvider:
    """Modele gerçek zamanlı sistem saati, günü ve yılını aktaran bağlam sağlayıcı."""

    _DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    _MONTHS = [
        "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
    ]

    def build_context(self, user_message: str = "") -> str:
        from datetime import datetime
        now = datetime.now()
        day_name = self._DAYS[now.weekday()]
        month_name = self._MONTHS[now.month]
        return (
            f"[GÜNCEL SİSTEM ZAMANI]: {now.day} {month_name} {now.year}, {day_name} "
            f"Saat {now.strftime('%H:%M')}. Geçerli takvim yılı {now.year}'dir. "
            f"Tarih, gün, ay veya yılla ilgili soruları bu gerçek zamanlı bilgiye göre yanıtla."
        )

