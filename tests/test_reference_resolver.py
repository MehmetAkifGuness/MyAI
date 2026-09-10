import unittest

from boru.context_reference_resolver import ConversationReferenceResolver
from boru.models import ChatMessage


class ConversationReferenceResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = ConversationReferenceResolver()

    def test_extract_recent_files(self):
        history = [
            ChatMessage("user", "main.py dosyasındaki build_application fonksiyonuna bak"),
            ChatMessage("assistant", "main.py dosyasını inceledim. Ayrıca config.json dosyası da var."),
        ]
        refs = self.resolver.extract_recent_references(history)
        self.assertIn("main.py", refs["files"])
        self.assertIn("config.json", refs["files"])

    def test_extract_recent_symbols(self):
        history = [
            ChatMessage("user", "def parse_input fonksiyonunda bir hata var mı?"),
            ChatMessage("assistant", "class ArchitectureManager içinde inceliyorum."),
        ]
        refs = self.resolver.extract_recent_references(history)
        self.assertIn("parse_input", refs["symbols"])
        self.assertIn("ArchitectureManager", refs["symbols"])

    def test_build_reference_context(self):
        history = [
            ChatMessage("user", "server.py üzerinde çalışalım."),
            ChatMessage("assistant", "server.py hazır, ne yapalım?"),
        ]
        context = self.resolver.build_reference_context(history)
        self.assertIn("[Konuşma Odak Bağlamı]", context)
        self.assertIn("`server.py`", context)

    def test_empty_history_yields_empty_context(self):
        context = self.resolver.build_reference_context([])
        self.assertEqual(context, "")


if __name__ == "__main__":
    unittest.main()
