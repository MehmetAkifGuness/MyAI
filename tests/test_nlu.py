import unittest

from boru.nlu.fuzzy_matcher import (
    damerau_levenshtein_distance,
    match_command_prefix,
    normalize_turkish,
)


class TurkishNormalizationTests(unittest.TestCase):
    def test_normalizes_turkish_letters_and_casing(self):
        self.assertEqual(normalize_turkish("İSTANBUL"), "istanbul")
        self.assertEqual(normalize_turkish("Şeker Çikolata Ağaç Öğrenci Üzüm"), "seker cikolata agac ogrenci uzum")
        self.assertEqual(normalize_turkish("ıslık"), "islik")
        self.assertEqual(normalize_turkish(""), "")


class DamerauLevenshteinDistanceTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(damerau_levenshtein_distance("kodla", "kodla"), 0)

    def test_single_insertion(self):
        self.assertEqual(damerau_levenshtein_distance("kodlaa", "kodla"), 1)

    def test_single_deletion(self):
        self.assertEqual(damerau_levenshtein_distance("kola", "kodla"), 1)

    def test_single_substitution(self):
        self.assertEqual(damerau_levenshtein_distance("kodli", "kodla"), 1)

    def test_adjacent_transposition(self):
        self.assertEqual(damerau_levenshtein_distance("kdola", "kodla"), 1)
        self.assertEqual(damerau_levenshtein_distance("kdolama", "kodlama"), 1)


class FuzzyCommandMatcherTests(unittest.TestCase):
    def setUp(self):
        self.coding_triggers = ["kodla", "coding", "kod değişikliği hazırla", "kodlama"]
        self.agent_triggers = ["ajan", "kod tabanını araştır"]
        self.web_triggers = ["web ara", "web oku", "web araştır", "internetten araştır"]

    def test_exact_matches_with_colon(self):
        result = match_command_prefix("kodla: dosya.py", self.coding_triggers)
        self.assertEqual(result, ("kodla", "dosya.py"))

    def test_typo_transposition_with_colon(self):
        result = match_command_prefix("kdola: dosya.py", self.coding_triggers)
        self.assertEqual(result, ("kodla", "dosya.py"))

    def test_typo_insertion_with_colon(self):
        result = match_command_prefix("kdolama: test ekle", self.coding_triggers)
        self.assertEqual(result, ("kodlama", "test ekle"))

    def test_turkish_ascii_diacritic_tolerance(self):
        result = match_command_prefix("kod degisikligi hazirla: main.py", self.coding_triggers)
        self.assertEqual(result, ("kod değişikliği hazırla", "main.py"))

        result = match_command_prefix("kod tabanini arastir: AssistantService", self.agent_triggers)
        self.assertEqual(result, ("kod tabanını araştır", "AssistantService"))

    def test_web_command_typo_tolerance(self):
        result = match_command_prefix("web arastir: Python json", self.web_triggers)
        self.assertEqual(result, ("web araştır", "Python json"))

        result = match_command_prefix("webe ara: Python doc", self.web_triggers)
        self.assertEqual(result, ("web ara", "Python doc"))

    def test_agent_command_typos(self):
        result = match_command_prefix("ajn: hangi dosya", self.agent_triggers)
        self.assertEqual(result, ("ajan", "hangi dosya"))

        result = match_command_prefix("ajani: bu sinif nerede", self.agent_triggers)
        self.assertEqual(result, ("ajan", "bu sinif nerede"))

    def test_colonless_commands(self):
        result = match_command_prefix("kdola main.py incele", self.coding_triggers)
        self.assertEqual(result, ("kodla", "main.py incele"))

        result = match_command_prefix("web arastir Python async", self.web_triggers)
        self.assertEqual(result, ("web araştır", "Python async"))

    def test_non_matching_conversational_messages(self):
        self.assertIsNone(match_command_prefix("kodlar çok güzel yazılmış", self.coding_triggers))
        self.assertIsNone(match_command_prefix("hava bugün çok güzel", self.coding_triggers))
        self.assertIsNone(match_command_prefix("", self.coding_triggers))
        self.assertIsNone(match_command_prefix("   ", self.coding_triggers))


class CodingParserTypoIntegrationTests(unittest.TestCase):
    def setUp(self):
        from boru.coding.parser import RuleBasedCodingRequestParser
        self.parser = RuleBasedCodingRequestParser()

    def test_parses_typo_kdola(self):
        req = self.parser.parse("kdola: main.py dosyasına yeni fonksiyon ekle")
        self.assertIsNotNone(req)
        self.assertIn("main.py", req.task)

    def test_parses_typo_kdolama(self):
        req = self.parser.parse("kdolama: tests/test_nlu.py düzelt")
        self.assertIsNotNone(req)
        self.assertIn("test_nlu.py", req.task)

    def test_parses_turkish_ascii_kod_degisikligi(self):
        req = self.parser.parse("kod degisikligi hazirla: bug fix")
        self.assertIsNotNone(req)
        self.assertIn("bug fix", req.task)

    def test_parses_colonless_kdola(self):
        req = self.parser.parse("kdola utils.py refactor")
        self.assertIsNotNone(req)
        self.assertIn("utils.py", req.task)

    def test_recognizes_intent_with_typo(self):
        self.assertTrue(self.parser.is_coding_intent("kdola: main.py"))
        self.assertTrue(self.parser.is_coding_intent("coing: main.py"))
        self.assertFalse(self.parser.is_coding_intent("bugün hava yağmurlu"))


class SmartEditFuzzySliceTests(unittest.TestCase):
    def test_crlf_vs_lf_slice_location(self):
        from boru.nlu.fuzzy_matcher import locate_unique_fuzzy_slice
        original = "def compute():\r\n    x = 10\r\n    return x * 2\r\n"
        old_text = "def compute():\n    x = 10\n    return x * 2"
        res = locate_unique_fuzzy_slice(original, old_text)
        self.assertIsNotNone(res)
        start, end = res
        self.assertEqual(original[start:end], "def compute():\r\n    x = 10\r\n    return x * 2\r\n")

    def test_trailing_whitespace_slice_location(self):
        from boru.nlu.fuzzy_matcher import locate_unique_fuzzy_slice
        original = "def worker():   \n    val = True   \n    return val\n"
        old_text = "def worker():\n    val = True\n    return val"
        res = locate_unique_fuzzy_slice(original, old_text)
        self.assertIsNotNone(res)
        start, end = res
        self.assertEqual(original[start:end], "def worker():   \n    val = True   \n    return val\n")

    def test_ambiguous_matches_return_none(self):
        from boru.nlu.fuzzy_matcher import locate_unique_fuzzy_slice
        original = "count = 0\ncount = 0\n"
        old_text = "count = 0"
        self.assertIsNone(locate_unique_fuzzy_slice(original, old_text))

    def test_workspace_prepare_exact_replacement_with_newline_variance(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from boru.tools.edit_workspace import SafeEditWorkspace
        from boru.tools.edit_models import EditRequest

        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "sample.py"
            file_path.write_bytes(b"def greet():\r\n    return 'hi'\r\n")
            ws = SafeEditWorkspace(tmpdir)

            # Model generates LF newlines, file has CRLF
            proposal = ws.prepare_exact_replacement(
                EditRequest(
                    path="sample.py",
                    old_text="def greet():\n    return 'hi'",
                    new_text="def greet():\r\n    return 'hello world'\r\n",
                )
            )
            self.assertIn("hello world", proposal.updated_content)


if __name__ == "__main__":
    unittest.main()
