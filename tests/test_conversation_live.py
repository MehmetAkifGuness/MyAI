"""Opt-in local model dialogue test; uses fictional conversation, no user memory."""
import json
import os
import unittest

from boru.agent.coordinator import GeneralAgentCoordinator
from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.conversation_quality import ConversationalChatModel, build_conversation_model
from boru.memory.intent import RuleBasedMemoryIntentDetector
from boru.memory.relevant_query_resolver import RelevantMemoryQueryResolver
from boru.prompts import SystemPromptFactory
from unittest.mock import Mock


@unittest.skipUnless(os.getenv('BORU_LIVE_CHAT') == '1', 'Canlı sohbet testi isteğe bağlı')
class LiveConversationTests(unittest.TestCase):
    def test_two_turn_casual_conversation(self):
        model = build_conversation_model(os.getenv('BORU_LIVE_CHAT_MODEL', 'llama3.1:latest'))
        self.addCleanup(model.close)
        history = ConversationHistory(max_turns=5)
        memory = Mock()
        assistant = AssistantService(ConversationalChatModel(model), history,
            SystemPromptFactory(conversational=True), direct_response_resolvers=[
                GeneralAgentCoordinator(Mock()),
                RelevantMemoryQueryResolver(memory, intent_detector=RuleBasedMemoryIntentDetector(history)),
            ])
        first = assistant.reply('Yarın matematik sınavım var, biraz gerginim. Tavsiye listesi istemiyorum, biraz sohbet edelim.')
        second = assistant.reply('Az önce neye hazırlandığımı söylediğimi hatırlıyor musun?')
        print('\nLIVE_CHAT=' + json.dumps([first, second], ensure_ascii=True), flush=True)
        self.assertNotIn('AJAN RAPORU', first + second)
        self.assertIn('matematik', second.casefold())
        self.assertNotIn('düzgün bir yanıt oluşturamadım', first + second)
        memory.search.assert_not_called()

    def test_correction_survives_topic_switch(self):
        model = build_conversation_model(os.getenv('BORU_LIVE_CHAT_MODEL', 'llama3.1:latest'))
        self.addCleanup(model.close)
        assistant = AssistantService(ConversationalChatModel(model), ConversationHistory(max_turns=6),
                                     SystemPromptFactory(conversational=True))
        answers = []
        for message in (
            'Kedimin adı Fındık, köpeğimin adı Bulut. Kısaca yanıt ver.',
            'Yanlış yazdım: kedimin adı artık Tarçın. Köpeğimin adı değişmedi. Kısaca yanıt ver.',
            'Konuyu değiştirelim: yağmurlu havada yürümeyi seviyorum. Tek cümleyle yanıtla.',
            'Az önce söylediğim kedimin ve köpeğimin güncel adları neydi? Sadece iki adı yaz.',
        ):
            answers.append(assistant.reply(message))
        print('\nLIVE_CHAT_TOPIC_SWITCH=' + json.dumps(answers, ensure_ascii=True), flush=True)
        self.assertIn('tarçın', answers[-1].casefold())
        self.assertIn('bulut', answers[-1].casefold())
        self.assertNotIn('fındık', answers[-1].casefold())
        self.assertNotIn('?', answers[-1])
