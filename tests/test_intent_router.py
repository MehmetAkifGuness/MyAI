import unittest

from boru.nlu.intent_router import FreeFormIntentRouter, RoutedIntent


class FreeFormIntentRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = FreeFormIntentRouter()

    def test_routes_coding_intent_without_prefix(self):
        user_msg = "main.py dosyasına yeni bir loglama fonksiyonu ekle"
        result = self.router.route(user_msg)
        self.assertEqual(result.intent, RoutedIntent.CODING)
        self.assertTrue(result.transformed_message.startswith("kodla: "))
        self.assertIn("loglama", result.transformed_message)

    def test_routes_improvement_intent_without_prefix(self):
        user_msg = "boru/config.py dosyasındaki hatayı çöz ve refactor et"
        result = self.router.route(user_msg)
        self.assertEqual(result.intent, RoutedIntent.IMPROVEMENT)
        self.assertTrue(result.transformed_message.startswith("iyileştir: boru/config.py |"))

    def test_routes_testing_intent(self):
        user_msg = "tests/test_v01.py dosyasını test et"
        result = self.router.route(user_msg)
        self.assertEqual(result.intent, RoutedIntent.TESTING)
        self.assertEqual(result.transformed_message, "test ajanı: tests/test_v01.py")

    def test_preserves_explicit_commands(self):
        user_msg = "kodla: calculate fonksiyonu yaz"
        result = self.router.route(user_msg)
        self.assertEqual(result.transformed_message, user_msg)

    def test_general_chat_fallback(self):
        user_msg = "Selam, bugün hava nasıl?"
        result = self.router.route(user_msg)
        self.assertEqual(result.intent, RoutedIntent.GENERAL_CHAT)
        self.assertEqual(result.transformed_message, user_msg)


if __name__ == "__main__":
    unittest.main()
