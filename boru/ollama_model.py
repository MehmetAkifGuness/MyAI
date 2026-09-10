from collections.abc import Mapping
from threading import RLock
from time import monotonic
from typing import Any, Sequence

import ollama

from boru.models import ChatMessage
from boru.performance import PerformanceMonitor


class OllamaChatModel:
    """Ollama Python istemcisini ChatModel sözleşmesine uyarlayan adapter."""

    def __init__(
        self,
        model_name: str,
        chat_client: Any = None,
        warmup_client: Any = None,
        structured_chat_client: Any = None,
        *,
        request_timeout_seconds: float = 180.0,
        structured_timeout_seconds: float | None = None,
        structured_num_predict: int = 384,
        keep_alive: str = "10m",
        performance_monitor: PerformanceMonitor | None = None,
        structured_thinking: bool | None = None,
        chat_temperature: float | None = None,
        chat_num_predict: int | None = None,
        chat_thinking: bool | None = None,
    ):
        cleaned_model_name = model_name.strip()
        if not cleaned_model_name:
            raise ValueError("Model adı boş olamaz.")
        if request_timeout_seconds <= 0:
            raise ValueError("Model istek zaman aşımı pozitif olmalıdır.")
        if structured_timeout_seconds is not None and structured_timeout_seconds <= 0:
            raise ValueError("Yapılandırılmış model zaman aşımı pozitif olmalıdır.")
        if structured_num_predict < 1:
            raise ValueError("Yapılandırılmış model çıktı sınırı pozitif olmalıdır.")
        if not keep_alive.strip():
            raise ValueError("Model keep_alive değeri boş olamaz.")
        if chat_temperature is not None and (isinstance(chat_temperature, bool) or not 0 <= chat_temperature <= 2):
            raise ValueError('Sohbet sıcaklığı 0 ile 2 arasında olmalıdır.')
        if chat_num_predict is not None and (type(chat_num_predict) is not int or not 1 <= chat_num_predict <= 8192):
            raise ValueError('Sohbet çıktı sınırı 1-8192 arasında tam sayı olmalıdır.')
        if chat_thinking is not None and type(chat_thinking) is not bool:
            raise ValueError('Sohbet düşünme ayarı bool olmalıdır.')

        self._model_name = cleaned_model_name
        self._owned_clients = []
        if chat_client is None:
            client = ollama.Client(
                timeout=request_timeout_seconds
            )
            self._chat_client = client.chat
            self._warmup_client = client.generate
            structured_client = ollama.Client(
                timeout=structured_timeout_seconds or request_timeout_seconds
            )
            self._owned_clients = [client, structured_client]
            self._structured_chat_client = structured_client.chat
        else:
            self._chat_client = chat_client
            self._warmup_client = warmup_client
            self._structured_chat_client = structured_chat_client or chat_client
        self._structured_num_predict = structured_num_predict
        self._keep_alive = keep_alive.strip()
        self._performance_monitor = performance_monitor
        self._structured_thinking = structured_thinking
        self._chat_thinking = chat_thinking
        self._chat_options = {}
        if chat_temperature is not None:
            self._chat_options['temperature'] = chat_temperature
        if chat_num_predict is not None:
            self._chat_options['num_predict'] = chat_num_predict
        self._lock = RLock()

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        return self._generate(
            messages,
        )

    def generate_structured(
        self,
        messages: Sequence[ChatMessage],
        schema: Mapping[str, Any],
    ) -> str:
        return self._generate(
            messages,
            response_format=dict(schema),
        )

    def _generate(
        self,
        messages: Sequence[ChatMessage],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        options: dict[str, Any] = {
            "model": self._model_name,
            "messages": [message.to_dict() for message in messages],
            "stream": False,
            "keep_alive": self._keep_alive,
        }

        if response_format is not None:
            options["format"] = response_format
            if self._structured_thinking is not None:
                options['think'] = self._structured_thinking
            options["options"] = {
                "temperature": 0,
                "num_predict": self._structured_num_predict,
            }
        else:
            if self._chat_thinking is not None:
                options['think'] = self._chat_thinking
            if self._chat_options:
                options['options'] = dict(self._chat_options)

        operation = "model.structured" if response_format is not None else "model.chat"
        started = monotonic()
        succeeded = False
        try:
            with self._lock:
                client = (
                    self._structured_chat_client
                    if response_format is not None
                    else self._chat_client
                )
                response = client(
                    **options,
                )
            succeeded = True
        finally:
            if self._performance_monitor is not None:
                self._performance_monitor.record(
                    operation,
                    monotonic() - started,
                    succeeded,
                )
        response_message = self._field(response, "message")
        if response_message is None:
            raise RuntimeError("Ollama yanıtında message alanı bulunamadı.")

        content = self._field(response_message, "content", "")
        if content and response_format is None and self._chat_options and self._field(response, 'done_reason') == 'length':
            return str(content or '') + '\n\n[Yanıt çıktı sınırına ulaştı; tamamı üretilemedi.]'
        return str(content or "")

    def warmup(self) -> None:
        if self._warmup_client is None:
            return
        with self._lock:
            self._warmup_client(
                model=self._model_name,
                prompt="",
                keep_alive=self._keep_alive,
            )

    def close(self) -> None:
        """Release only clients created by this adapter; injected clients remain caller-owned."""
        with self._lock:
            for client in self._owned_clients:
                client.close()
            self._owned_clients.clear()
