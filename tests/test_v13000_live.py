"""Explicit opt-in network/model smoke test; public docs only, no repository content sent."""
import json
import os
import unittest

from boru.ollama_model import OllamaChatModel
from boru.web.coordinator import WebResearchCoordinator


@unittest.skipUnless(os.getenv('BORU_LIVE_WEB') == '1', 'Canlı web/model testi isteğe bağlı')
class LiveWebTests(unittest.TestCase):
    def test_official_document_with_local_model(self):
        model = OllamaChatModel('qwen2.5-coder:7b', structured_timeout_seconds=60, structured_num_predict=1400)
        coordinator = WebResearchCoordinator(model)
        result = coordinator.resolve('web oku: https://docs.python.org/3/library/json.html | json.loads ne yapar? Geçersiz JSON için hangi hata oluşur?')
        print('\nLIVE_WEB_RESULT=' + json.dumps(result, ensure_ascii=True), flush=True)
        self.assertIn('WEB YANITI', result)
        self.assertIn('JSONDecodeError', result)
        self.assertIn('[1]', result)
        self.assertIn('https://docs.python.org/3/library/json.html', result)
        self.assertNotIn('yeterli bilgi bulunamadı', result)
