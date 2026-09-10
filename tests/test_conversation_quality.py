import os
import unittest
from unittest.mock import Mock, patch

from boru.agent.coordinator import GeneralAgentCoordinator
from boru.assistant import AssistantService
from boru.config import AppSettings
from boru.context import ConversationContextBuilder
from boru.conversation import ConversationHistory
from boru.conversation_quality import ConversationalChatModel
from boru.memory.intent import RuleBasedMemoryIntentDetector
from boru.memory.relevant_query_resolver import RelevantMemoryQueryResolver
from boru.modeling.structured import StructuredModelCascade
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory


class ConversationQualityTests(unittest.TestCase):
    def test_daily_questions_do_not_call_code_agent(self):
        agent = Mock()
        resolver = GeneralAgentCoordinator(agent)
        for message in ('Ankara nerede?', 'OpenAI nasıl çalışıyor?', 'YouTube nasıl kullanılır?',
                        'Bugün çok yoruldum, biraz sohbet edelim.', 'Yarınki sınav için ne yapmalıyım?'):
            with self.subTest(message=message):
                self.assertIsNone(resolver.resolve(message))
        agent.run.assert_not_called()
        resolver.resolve('AssistantService sınıfı hangi dosyada?')
        agent.run.assert_called_once()

    def test_followup_uses_recent_conversation_not_unknown_persistent_memory(self):
        history = ConversationHistory(max_turns=5)
        history.add_turn('Yarın matematik sınavım var.', 'Sınavdan önce nasıl hissediyorsun?')
        memory = Mock()
        model = Mock(generate=Mock(return_value='Yarınki matematik sınavına hazırlanıyorsun.'))
        detector = RuleBasedMemoryIntentDetector(history)
        resolver = RelevantMemoryQueryResolver(memory, intent_detector=detector)
        assistant = AssistantService(ConversationalChatModel(model), history,
                                     SystemPromptFactory(conversational=True), direct_response_resolvers=[resolver])
        result = assistant.reply('Az önce neye hazırlandığımı söylediğimi hatırlıyor musun?')
        self.assertIn('matematik', result)
        memory.search.assert_not_called()
        self.assertIn('Yarın matematik sınavım var.', str(model.generate.call_args.args[0]))
        self.assertTrue(detector.is_memory_relevant('Hafızanda projem için ne kayıtlı?'))
        self.assertTrue(detector.is_memory_relevant('Daha önce kullandığım editörü hatırlıyor musun?'))

    def test_repair_preserves_history_and_uses_configured_fallback(self):
        question = 'Bugün neden böyle hissettiğimi anlatayım mı?'
        primary = Mock(generate=Mock(return_value=question))
        fallback = Mock(generate=Mock(return_value='İstersen anlat, seni dinliyorum.'))
        messages = [ChatMessage('system', 'Türkçe yanıtla.'), ChatMessage('user', 'Yoruldum.'),
                    ChatMessage('assistant', 'Yoğun bir gün müydü?'), ChatMessage('user', question)]
        result = ConversationalChatModel(StructuredModelCascade(primary, fallback)).generate(messages)
        self.assertIn('dinliyorum', result)
        self.assertEqual(fallback.generate.call_args.args[0][:4], messages)
        primary.generate.assert_called_once()

    def test_repetition_is_retried_only_once(self):
        repeated = 'Bugün çok yorulmuş olmanı anlayabiliyorum. ' * 3
        model = Mock(generate=Mock(return_value=repeated))
        result = ConversationalChatModel(model).generate([ChatMessage('user', 'Bugün yoruldum.')])
        self.assertEqual(model.generate.call_count, 2)
        self.assertIn('düzgün bir yanıt oluşturamadım', result)
        self.assertNotIn(repeated, result)

    def test_recall_guidance_preserves_evidence_and_original_question(self):
        model = Mock(generate=Mock(return_value='Cuma günü.'))
        messages = [ChatMessage('system', 'Türkçe yanıtla.'),
                    ChatMessage('user', 'Toplantı cuma günü.'), ChatMessage('assistant', 'Anladım.'),
                    ChatMessage('user', 'Az önce toplantının ne zaman olduğunu söylemiştim?')]
        ConversationalChatModel(model).generate(messages)
        sent = model.generate.call_args.args[0]
        self.assertEqual(sent[:3], messages[:3])
        self.assertEqual(sent[-1], messages[-1])
        self.assertEqual(sent[-2].role, 'system')
        self.assertEqual(len(messages), 4)

    def test_listening_request_does_not_become_questionnaire(self):
        model = Mock(generate=Mock(side_effect=['Ne oldu? Neden? Nasıl?', 'Anlat istersen, dinliyorum.']))
        result = ConversationalChatModel(model).generate([
            ChatMessage('user', 'Tavsiye istemiyorum, biraz içimi dökmek istiyorum.')])
        self.assertEqual(result, 'Anlat istersen, dinliyorum.')
        self.assertEqual(model.generate.call_count, 2)

    def test_thinking_is_hidden_but_code_is_preserved(self):
        model = Mock(generate=Mock(return_value='<think>private reasoning</think>Merhaba!'))
        self.assertEqual(ConversationalChatModel(model).generate([ChatMessage('user', 'Merhaba')]), 'Merhaba!')
        self.assertEqual(model.generate.call_count, 1)
        code = '```python\nprint("hello")\nprint("hello")\n```'
        model.generate.return_value = code
        self.assertEqual(ConversationalChatModel(model).generate([ChatMessage('user', 'örnek kod')]), code)

    def test_large_report_does_not_evict_entire_recent_conversation(self):
        history = [ChatMessage('user', 'Yarın sınavım var.'), ChatMessage('assistant', 'Anladım.'),
                   ChatMessage('user', 'web oku: docs'), ChatMessage('assistant', 'start ' + 'x' * 9000 + ' end')]
        context = ConversationContextBuilder(max_characters=6000, max_turn_characters=3000).build(history)
        self.assertIn(history[0], context)
        self.assertLessEqual(sum(len(m.content) for m in context), 6000)
        self.assertIn('[bağlam kısaltıldı]', context[-1].content)
        self.assertTrue(context[-1].content.endswith(' end'))
        self.assertEqual(len(history[-1].content), 9010)

    def test_separate_chat_model_setting_does_not_change_coding_model(self):
        with patch.dict(os.environ, {'BORU_MODEL': 'coder', 'BORU_CHAT_MODEL': 'conversational'}, clear=True):
            settings = AppSettings.from_env()
        self.assertEqual(settings.model_name, 'coder')
        self.assertEqual(settings.chat_model_name, 'conversational')
