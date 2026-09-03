from collections import deque
from threading import RLock

from boru.models import ChatMessage


class ConversationHistory:
    """Yalnızca kısa süreli sohbet geçmişini yönetir."""

    MESSAGES_PER_TURN = 2

    def __init__(self, max_turns: int = 10):
        if max_turns < 1:
            raise ValueError("max_turns en az 1 olmalıdır.")

        self._messages: deque[ChatMessage] = deque(
            maxlen=max_turns * self.MESSAGES_PER_TURN
        )
        self._lock = RLock()

    def snapshot(self) -> list[ChatMessage]:
        with self._lock:
            return list(self._messages)

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        user_text = user_message.strip()
        assistant_text = assistant_message.strip()

        if not user_text:
            raise ValueError("Kullanıcı mesajı boş olamaz.")
        if not assistant_text:
            raise ValueError("Asistan mesajı boş olamaz.")

        with self._lock:
            self._messages.append(ChatMessage(role="user", content=user_text))
            self._messages.append(ChatMessage(role="assistant", content=assistant_text))

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()