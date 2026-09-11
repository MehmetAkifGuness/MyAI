from collections.abc import Sequence

from boru.context import ConversationContextBuilder
from boru.context_reference_resolver import ConversationReferenceResolver
from boru.nlu.intent_router import FreeFormIntentRouter
from boru.contracts import (
    AssistantContextProvider,
    ChatModel,
    ContextBuilder,
    DirectResponseResolver,
    MessageObserver,
)
from boru.conversation import ConversationHistory
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory


class AssistantService:
    """
    Kullanıcı mesajlarını genişletilebilir bir
    pipeline üzerinden işleyen ana uygulama servisi.
    """

    def __init__(
        self,
        chat_model: ChatModel,
        conversation_history: ConversationHistory,
        prompt_factory: SystemPromptFactory,
        context_builder: ContextBuilder | None = None,
        message_observers: Sequence[MessageObserver] = (),
        direct_response_resolvers: Sequence[
            DirectResponseResolver
        ] = (),
        context_providers: Sequence[
            AssistantContextProvider
        ] = (),
    ):
        self._chat_model = chat_model
        self._history = conversation_history
        self._prompt_factory = prompt_factory

        self._context_builder = (
            context_builder
            or ConversationContextBuilder()
        )

        self._message_observers = tuple(
            message_observers
        )

        self._direct_response_resolvers = tuple(
            direct_response_resolvers
        )

        self._context_providers = tuple(
            context_providers
        )
        self._reference_resolver = ConversationReferenceResolver()
        self._intent_router = FreeFormIntentRouter()

    def reply(
        self,
        user_message: str,
    ) -> str:
        user_text = user_message.strip()

        if not user_text:
            raise ValueError(
                "Kullanıcı mesajı boş olamaz."
            )

        self._notify_observers(
            user_text
        )

        # 1. Doğrudan orijinal metinle dene
        direct_answer = (
            self._resolve_direct_response(
                user_text
            )
        )

        # 2. Doğrudan çözülemediyse serbest doğal dil niyet yönlendiricisini dene
        if direct_answer is None:
            routed = self._intent_router.route(user_text)
            if routed.transformed_message != user_text:
                direct_answer = self._resolve_direct_response(routed.transformed_message)

        if direct_answer is not None:
            self._history.add_turn(
                user_text,
                direct_answer,
            )

            return direct_answer

        messages = (
            self._build_model_messages(
                user_text
            )
        )

        assistant_text = (
            self._chat_model
            .generate(messages)
            .strip()
        )

        if not assistant_text:
            raise RuntimeError(
                "Dil modeli boş yanıt döndürdü."
            )

        self._history.add_turn(
            user_text,
            assistant_text,
        )

        return assistant_text

    def reply_stream(
        self,
        user_message: str,
    ):
        """Yield response chunks sequentially. If direct response applies, yield it in one piece."""
        user_text = user_message.strip()

        if not user_text:
            raise ValueError(
                "Kullanıcı mesajı boş olamaz."
            )

        self._notify_observers(
            user_text
        )

        direct_answer = (
            self._resolve_direct_response(
                user_text
            )
        )

        if direct_answer is None:
            routed = self._intent_router.route(user_text)
            if routed.transformed_message != user_text:
                direct_answer = self._resolve_direct_response(routed.transformed_message)

        if direct_answer is not None:
            self._history.add_turn(
                user_text,
                direct_answer,
            )
            yield direct_answer
            return

        messages = (
            self._build_model_messages(
                user_text
            )
        )

        stream_func = getattr(self._chat_model, "generate_stream", None)
        if callable(stream_func):
            accumulated_chunks: list[str] = []
            for chunk in stream_func(messages):
                accumulated_chunks.append(chunk)
                yield chunk

            full_text = "".join(accumulated_chunks).strip()
            if not full_text:
                raise RuntimeError(
                    "Dil modeli boş yanıt döndürdü."
                )

            self._history.add_turn(
                user_text,
                full_text,
            )
        else:
            # Fallback to standard generate
            assistant_text = (
                self._chat_model
                .generate(messages)
                .strip()
            )
            if not assistant_text:
                raise RuntimeError(
                    "Dil modeli boş yanıt döndürdü."
                )

            self._history.add_turn(
                user_text,
                assistant_text,
            )
            yield assistant_text

    def reset_conversation(
        self,
    ) -> None:
        self._history.clear()

    def _notify_observers(
        self,
        user_message: str,
    ) -> None:
        for observer in self._message_observers:
            observer.observe(
                user_message
            )

    def _resolve_direct_response(
        self,
        user_message: str,
    ) -> str | None:
        # 1. Öncelik: PC Yönetim ve Sistem Araçları (Uygulama açma, ses, pil vb.)
        try:
            from boru.tools.system_tools import resolve_system_command
            sys_res = resolve_system_command(user_message)
            if sys_res is not None:
                return sys_res
        except Exception:
            pass

        for resolver in (
            self._direct_response_resolvers
        ):
            answer = resolver.resolve(
                user_message
            )

            if answer is None:
                continue

            cleaned_answer = answer.strip()

            if not cleaned_answer:
                raise RuntimeError(
                    (
                        "Doğrudan yanıt "
                        "çözücüsü boş yanıt "
                        "döndürdü."
                    )
                )

            return cleaned_answer

        return None

    def _build_model_messages(
        self,
        user_text: str,
    ) -> list[ChatMessage]:
        context_messages = (
            self._context_builder.build(
                self._history.snapshot()
            )
        )

        messages = [
            ChatMessage(
                role="system",
                content=(
                    self._prompt_factory
                    .build()
                ),
            )
        ]

        for provider in (
            self._context_providers
        ):
            provider_context = (
                provider
                .build_context(
                    user_text
                )
                .strip()
            )

            if provider_context:
                messages.append(
                    ChatMessage(
                        role="system",
                        content=(
                            provider_context
                        ),
                    )
                )

        ref_context = self._reference_resolver.build_reference_context(
            self._history.snapshot()
        )
        if ref_context:
            messages.append(
                ChatMessage(
                    role="system",
                    content=ref_context,
                )
            )

        messages.extend(
            context_messages
        )

        messages.append(
            ChatMessage(
                role="user",
                content=user_text,
            )
        )

        return messages