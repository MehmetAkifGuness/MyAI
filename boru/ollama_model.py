from typing import Any, Sequence

import ollama

from boru.models import ChatMessage


class OllamaChatModel:
    """Ollama Python istemcisini ChatModel sözleşmesine uyarlayan adapter."""

    def __init__(self, model_name: str, chat_client: Any = None):
        cleaned_model_name = model_name.strip()
        if not cleaned_model_name:
            raise ValueError("Model adı boş olamaz.")

        self._model_name = cleaned_model_name
        self._chat_client = chat_client or ollama.chat

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        response = self._chat_client(
            model=self._model_name,
            messages=[message.to_dict() for message in messages],
            stream=False,
        )
        response_message = self._field(response, "message")
        if response_message is None:
            raise RuntimeError("Ollama yanıtında message alanı bulunamadı.")

        content = self._field(response_message, "content", "")
        return str(content or "")