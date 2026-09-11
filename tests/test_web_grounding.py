import unittest
from unittest.mock import Mock

from boru.context import AutonomousWebGroundingContextProvider
from boru.nlu.intent_router import FreeFormIntentRouter
from boru.web.coordinator import WebResearchCoordinator


class TestAutonomousWebGrounding(unittest.TestCase):
    def test_greetings_and_code_do_not_trigger_web_search(self):
        search_mock = Mock()
        provider = AutonomousWebGroundingContextProvider(search_fn=search_mock)

        self.assertEqual(provider.build_context('merhaba nasılsın'), '')
        self.assertEqual(provider.build_context('selam börü'), '')
        self.assertEqual(provider.build_context('kodla: def hello(): pass'), '')
        self.assertEqual(provider.build_context('sesi aç'), '')
        self.assertEqual(provider.build_context('az önce ne demiştim hatırlıyor musun'), '')
        search_mock.assert_not_called()

    def test_factual_and_research_queries_trigger_web_grounding(self):
        search_mock = Mock(return_value=(True, 'Canlı sonuç: 2026 asgari ücreti...'))
        provider = AutonomousWebGroundingContextProvider(search_fn=search_mock)

        context = provider.build_context('2026 yılı asgari ücreti ne kadar olacak?')
        self.assertIn('[GÜNCEL DOĞRULANMIŞ WEB VE ARAŞTIRMA VERİLERİ]', context)
        self.assertIn('2026 asgari ücreti', context)
        self.assertIn('KESİNLİKLE KULLANMA', context)
        search_mock.assert_called_once()

    def test_failed_search_injects_anti_hallucination_constraint(self):
        search_mock = Mock(return_value=(False, 'Sonuç yok'))
        provider = AutonomousWebGroundingContextProvider(search_fn=search_mock)

        context = provider.build_context('Bilinmeyen bir konuda soru nedir?')
        self.assertIn('[BİLGİ VE ARAŞTIRMA KISITI]', context)
        self.assertIn('ezberden bilgi uydurma', context)
        search_mock.assert_called_once()

    def test_intent_router_transforms_arastir_prefix(self):
        router = FreeFormIntentRouter()
        res = router.route('araştır: kuantum bilgisayarlar')
        self.assertEqual(res.transformed_message, 'web araştır: kuantum bilgisayarlar')

    def test_intent_router_transforms_natural_research(self):
        router = FreeFormIntentRouter()
        res = router.route('togg yeni modeli konusunu araştır')
        self.assertEqual(res.transformed_message, 'web araştır: togg yeni modeli')

    def test_web_coordinator_accepts_arastir_command(self):
        model = Mock()
        client = Mock()
        search = Mock(search=Mock(return_value=[]))
        coordinator = WebResearchCoordinator(model, client=client, search=search)
        res = coordinator.resolve('araştır: mars kolonisi')
        self.assertIn('WEB ARAMA', res)
        search.search.assert_called_once_with('mars kolonisi')
