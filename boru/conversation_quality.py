"""Bounded quality checks for ordinary conversation; never executes model output."""
import re

from boru.modeling.structured import structured_model_for_attempt
from boru.models import ChatMessage


def build_conversation_model(model_name, *, fallback_name='', performance_monitor=None, timeout=90):
    """Separate chat settings so conversational tuning cannot affect coding tools."""
    from boru.ollama_model import OllamaChatModel
    from boru.modeling.structured import StructuredModelCascade

    def create(name):
        return OllamaChatModel(name, request_timeout_seconds=timeout,
                              chat_temperature=0.35, chat_num_predict=1024,
                              chat_thinking=False if name.startswith('qwen3') else None,
                              performance_monitor=performance_monitor)

    primary = create(model_name)
    if fallback_name and fallback_name != model_name:
        return StructuredModelCascade(primary, create(fallback_name))
    return primary


class ConversationalChatModel:
    def __init__(self, model):
        self.model = model

    def generate(self, messages):
        current = list(messages)
        question = next((m.content for m in reversed(messages) if m.role == 'user'), '')
        # A short, turn-specific reminder avoids burying the current need in a long prompt.
        folded = question.casefold().replace('\u0307', '')
        if re.search(r'\b(?:az önce|biraz önce|demin|hatırlıyor musun)\b', folded):
            index = max(i for i, message in enumerate(current) if message.role == 'user')
            current.insert(index, ChatMessage('system',
                'Bu tur kullanıcı konuşmada geçen bir bilgiyi soruyor. Görünen mesajlarda '
                'aradığı bilgi varsa onu tek kısa cevapla söyle. Bilgiyi bulamadığını iddia etme '
                've geçmiş oturumlar hakkında yorum yapma. Bilgi yoksa görünür bağlamda '
                'olmadığını söyle; tahmin etme. Yeni sohbet konusu veya takip sorusu ekleme. '
                'Asistanın önceki yanıtında bir ayrıntının geçmemesi, kullanıcının onu söylemediği '
                'anlamına gelmez. Öncelikle kullanıcının kendi mesajlarını esas al. '
                'Yeni bilgi veya eksik geçmiş uydurma.'))
        for attempt in (1, 2):
            raw = structured_model_for_attempt(self.model, attempt).generate(current)
            answer = self._clean(raw)
            problem = self._problem(answer, question)
            if not problem:
                return answer
            if attempt == 1:
                current.append(ChatMessage('system',
                    'Yanıt kalite denetimi: ' + problem +
                    ' Son kullanıcı mesajına konuşma bağlamını koruyarak yeniden yanıt ver. '
                    'Bu denetimi kullanıcıya anlatma.'))
        return 'Şu anda düzgün bir yanıt oluşturamadım. İstersen yeniden deneyebiliriz.'

    @staticmethod
    def _clean(value):
        if not isinstance(value, str):
            return ''
        value = value.strip()
        # Strip only a leading model reasoning block; quoted examples/code are preserved.
        if value.startswith('<think>'):
            end = value.find('</think>')
            if end < 0:
                return ''
            value = value[end + len('</think>'):].strip()
        return value

    @staticmethod
    def _problem(answer, question):
        if not answer:
            return 'Yanıt boş veya yalnızca iç düşünce içeriyor.'
        folded = question.casefold().replace('\u0307', '')
        if re.search(r'\btavsiye(?: listesi)? istemiyorum\b', folded) and answer.count('?') > 1:
            return 'Kullanıcı tavsiye değil dinlenmek istiyor; peş peşe sorular sorma. En fazla tek doğal soru sor.'
        if (len(question.split()) >= 4 or question.rstrip().endswith('?')) and re.sub(r'\W+', '', answer.casefold()) == re.sub(r'\W+', '', question.casefold()):
            return 'Kullanıcının mesajı yanıtlanmadan tekrar edilmiş.'
        if not answer.startswith('```') and re.match(r'^(?:system|assistant|user)\s*:', answer, re.I):
            return 'Yanıt konuşma rolü etiketiyle başlamış.'
        if '```' not in answer:
            sentences = [re.sub(r'\W+', ' ', s.casefold()).strip() for s in re.split(r'[.!?\n]+', answer)]
            long_sentences = [s for s in sentences if len(s.split()) >= 5]
            if len(long_sentences) >= 2 and len(set(long_sentences)) < len(long_sentences):
                return 'Aynı uzun cümle gereksiz yere tekrar edilmiş.'
        return ''
