import re
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
    TurnObserver,
)
from boru.conversation import ConversationHistory
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory


def _clean_metaprompt_leaks(text: str) -> str:
    cleaned = text.strip()
    patterns = [
        r"^(?:Doğru bilgi için sistem tarafından sağlanan [^\n\.\!]+[\.\!]\s*)",
        r"^(?:Sistem tarafından sağlanan güncel sistem saatini [^\n\.\!]+[\.\!]\s*)",
        r"^(?:Doğru bilgi için [^\n\.\!]+ esas alıyorum[\.\!]\s*)",
        r"^(?:Güncel sistem saatini ve [^\n\.\!]+ esas alıyorum[\.\!]\s*)",
    ]
    for p in patterns:
        cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


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
        turn_observers: Sequence[
            TurnObserver
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

        self._turn_observers = tuple(
            turn_observers
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
            self._notify_turn_observers(
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
        assistant_text = _clean_metaprompt_leaks(assistant_text)

        if not assistant_text:
            raise RuntimeError(
                "Dil modeli boş yanıt döndürdü."
            )

        self._history.add_turn(
            user_text,
            assistant_text,
        )
        self._notify_turn_observers(
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
            self._notify_turn_observers(
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
            full_text = _clean_metaprompt_leaks(full_text)
            if not full_text:
                raise RuntimeError(
                    "Dil modeli boş yanıt döndürdü."
                )

            self._history.add_turn(
                user_text,
                full_text,
            )
            self._notify_turn_observers(
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
            assistant_text = _clean_metaprompt_leaks(assistant_text)
            if not assistant_text:
                raise RuntimeError(
                    "Dil modeli boş yanıt döndürdü."
                )

            self._history.add_turn(
                user_text,
                assistant_text,
            )
            self._notify_turn_observers(
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

    def _notify_turn_observers(
        self,
        user_message: str,
        assistant_message: str,
    ) -> None:
        for observer in self._turn_observers:
            try:
                observer.observe_turn(
                    user_message,
                    assistant_message,
                )
            except Exception:
                pass

    def _resolve_direct_response(
        self,
        user_message: str,
    ) -> str | None:
        # 0. Öncelik: Otonom Hata Düzeltme & Alternatif Strateji (Self-Correction)
        # Kullanıcı "Hala açık", "Kapanmadı", "Çalışmadı" dediğinde önceki eylemi düzelt
        try:
            from boru.tools.self_corrector import SelfCorrectionDispatcher
            correction_res = SelfCorrectionDispatcher.handle_correction(user_message)
            if correction_res is not None:
                return correction_res
        except Exception:
            pass

        # 0.1 Öncelik: Kullanıcı Geri Bildirimi / Eleştiri / Hata Bildirimi (Feedback Intent)
        # Kullanıcının eleştirilerini ve düzeltmelerini asla komut veya arama olarak işletme!
        try:
            from boru.tools.semantic_router import SemanticIntentResolver
            fb_res = SemanticIntentResolver.resolve_feedback_intent(user_message)
            if fb_res is not None:
                return fb_res
        except Exception:
            pass

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

        # 2. Zincirleme / Çoklu Komutlar (örn: "müziği durdur ve masaüstünü göster")
        try:
            from boru.tools.compound_tools import resolve_compound_commands

            def _sub_resolve(text: str) -> str | None:
                try:
                    from boru.tools.system_tools import resolve_system_command
                    s = resolve_system_command(text)
                    if s is not None:
                        return s
                except Exception:
                    pass

                for res_item in self._direct_response_resolvers:
                    try:
                        ans = res_item.resolve(text)
                        if ans:
                            return ans.strip()
                    except Exception:
                        pass
                return None

            comp_ans = resolve_compound_commands(user_message, resolver_fn=_sub_resolve)
            if comp_ans is not None:
                return comp_ans
        except Exception:
            pass

        # 3. Esnek Anlamsal Niyet Çözücü (Semantic Intent Resolver)
        # Katı regex'lere takılmayan devrik, konuşma dili veya esnek Türkçe komutları doğrudan çözer
        try:
            from boru.tools.semantic_router import SemanticIntentResolver
            semantic_ans = SemanticIntentResolver.resolve_and_execute(user_message)
            if semantic_ans is not None:
                return semantic_ans
        except Exception:
            pass

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