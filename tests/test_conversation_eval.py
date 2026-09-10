import unittest
from unittest.mock import Mock, patch

from boru.conversation_eval import CASES, check_answer, evaluate
from boru.conversation_quality import build_conversation_model
from boru.models import ChatMessage
from boru.ollama_model import OllamaChatModel


class ConversationEvaluationTests(unittest.TestCase):
    def test_fact_words_inside_denial_are_not_success(self):
        checks = check_answer(CASES[1], 'Cuma matematik sınavı bilgisine ulaşamadım.')
        self.assertTrue(checks['required_facts'])
        self.assertFalse(checks['known_facts_not_denied'])

    def test_wrong_person_and_extra_questions_fail(self):
        self.assertFalse(check_answer(CASES[3], 'Ali.')['exact_answer'])
        self.assertTrue(check_answer(CASES[3], 'Defne.')['exact_answer'])
        self.assertFalse(check_answer(CASES[1], 'Cuma matematik sınavın var. Heyecanlı mısın?')['questions'])
        self.assertFalse(check_answer(CASES[4], 'Profilinde İstanbul kayıtlı.')['no_listed_inventions'])

    def test_benchmark_errors_remain_errors_and_contexts_are_isolated(self):
        model = Mock(generate=Mock(side_effect=[TimeoutError(), 'Cuma matematik sınavın var.']))
        with patch('builtins.print'):
            rows = evaluate('fake', model=model, limit=2)
        self.assertEqual(rows[0]['status'], 'error')
        self.assertEqual(rows[0]['error_type'], 'TimeoutError')
        self.assertEqual(rows[1]['status'], 'checks_passed')
        self.assertEqual(rows[1]['human_review'], 'not_rated')
        messages = model.generate.call_args.args[0]
        self.assertNotIn(CASES[0]['question'], str(messages))
        self.assertIn(CASES[1]['history'][0][0], str(messages))

    def test_chat_options_do_not_change_structured_generation(self):
        client = Mock(return_value={'message': {'content': 'yanıt'}})
        model = OllamaChatModel('qwen3.5:9b', chat_client=client, chat_temperature=0.35,
                                chat_num_predict=1024, chat_thinking=False, structured_thinking=True)
        messages = [ChatMessage('user', 'Merhaba')]
        model.generate(messages)
        self.assertEqual(client.call_args.kwargs['options'], {'temperature': 0.35, 'num_predict': 1024})
        self.assertFalse(client.call_args.kwargs['think'])
        model.generate_structured(messages, {'type': 'object'})
        self.assertEqual(client.call_args.kwargs['options'], {'temperature': 0, 'num_predict': 384})
        self.assertTrue(client.call_args.kwargs['think'])

    def test_legacy_options_unchanged_and_truncation_visible(self):
        client = Mock(return_value={'message': {'content': 'Yarım yanıt'}, 'done_reason': 'length'})
        legacy = OllamaChatModel('model', chat_client=client)
        self.assertEqual(legacy.generate([]), 'Yarım yanıt')
        self.assertNotIn('options', client.call_args.kwargs)
        self.assertNotIn('think', client.call_args.kwargs)
        bounded = OllamaChatModel('model', chat_client=client, chat_num_predict=1024)
        self.assertIn('tamamı üretilemedi', bounded.generate([]))
        client.return_value = {'message': {'content': ''}, 'done_reason': 'length'}
        self.assertEqual(bounded.generate([]), '')

    def test_invalid_chat_parameters_rejected(self):
        for values in ({'chat_temperature': float('nan')}, {'chat_temperature': True},
                       {'chat_num_predict': False}, {'chat_num_predict': 0},
                       {'chat_thinking': 'false'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                OllamaChatModel('fake', chat_client=Mock(), **values)

    def test_chat_factory_does_not_force_thinking_option_on_unsupported_model(self):
        with patch('boru.ollama_model.OllamaChatModel') as factory:
            build_conversation_model('llama3.1', fallback_name='qwen3.5:9b')
        self.assertIsNone(factory.call_args_list[0].kwargs['chat_thinking'])
        self.assertFalse(factory.call_args_list[1].kwargs['chat_thinking'])
        self.assertEqual(factory.call_args_list[0].kwargs['chat_num_predict'], 1024)

    def test_adapter_closes_owned_clients_only_and_is_idempotent(self):
        clients = [Mock(), Mock()]
        with patch('boru.ollama_model.ollama.Client', side_effect=clients):
            model = OllamaChatModel('fake')
        model.close()
        model.close()
        for client in clients:
            client.close.assert_called_once()
        external = Mock()
        OllamaChatModel('fake', chat_client=external).close()
        external.close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
