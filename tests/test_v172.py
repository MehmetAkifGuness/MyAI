import json
import unittest

from boru.architecture import ArchitectureRequest, ArchitectureStep, LLMArchitectAgent
from boru.tools import EditSource, ProjectFileSelection


PARSER_PATH = "boru/tools/command_parser.py"
MODELS_PATH = "boru/tools/command_models.py"


class StructuredModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate_structured(self, messages, schema):
        del schema
        self.calls.append(messages)
        return json.dumps(self.outputs.pop(0), ensure_ascii=False)


class Index:
    def list_editable_files(self):
        return (PARSER_PATH, MODELS_PATH)


class Selector:
    def select_files(self, *, request, available_paths):
        del request
        return ProjectFileSelection(available_paths)


class Workspace:
    _SOURCES = {
        PARSER_PATH: "class RuleBasedCommandRequestParser:\n    def parse(self, value): ...\n",
        MODELS_PATH: "class CommandKind(str): ...\nclass CommandRequest: ...\n",
    }

    def read_edit_source(self, path):
        return EditSource(path, self._SOURCES[path], "hash")


class CreationValidator:
    def validate_new_text_file(self, relative_path, content):
        del relative_path, content


def plan(*, grounded):
    if grounded:
        summary = "Güvenli komut ayrıştırma sözleşmesini genişlet."
        steps = [
            {
                "title": "1. RuleBasedCommandRequestParser kuralını genişlet",
                "description": "parse içinde yeni girdiyi doğrulayıp CommandRequest üret.",
                "files": [PARSER_PATH],
            },
            {
                "title": "2. CommandKind değerini tanımla",
                "description": "CommandRequest veri sözleşmesini geriye uyumlu tut.",
                "files": [MODELS_PATH],
            },
        ]
        tests = [
            "RuleBasedCommandRequestParser.parse için kabul ve ret durumlarını doğrula."
        ]
    else:
        summary = "Mimari Plan"
        steps = [{
            "title": "1. Komut isteğini işle",
            "description": "Komutları tanımlayın ve işleyin.",
            "files": [PARSER_PATH, MODELS_PATH],
        }]
        tests = ["Komut testi yapın."]
    return {
        "summary": summary,
        "existing_files": [PARSER_PATH, MODELS_PATH],
        "new_files": [],
        "steps": steps,
        "risks": ["Mevcut komutların ayrıştırılması değişebilir."],
        "tests": tests,
        "notes": ["Yürütme katmanını değiştirme."],
    }


class V172ArchitectQualityTests(unittest.TestCase):
    def test_step_title_removes_model_generated_numbering(self):
        step = ArchitectureStep("2. Parserı güncelle", "Açıklama")
        self.assertEqual(step.title, "Parserı güncelle")

    def test_generic_plan_uses_source_grounded_fallback_without_second_call(self):
        model = StructuredModel([plan(grounded=False), plan(grounded=True)])
        agent = LLMArchitectAgent(
            chat_model=model,
            file_index=Index(),
            file_selector=Selector(),
            workspace=Workspace(),
            creation_validator=CreationValidator(),
        )

        result = agent.plan(
            ArchitectureRequest("yeni güvenli komutu planla", (PARSER_PATH, MODELS_PATH))
        )

        self.assertEqual(len(model.calls), 1)
        self.assertEqual(result.steps[0].title, "RuleBasedCommandRequestParser ayrıştırmasını genişlet")
        self.assertIn("RuleBasedCommandRequestParser", result.tests[0])


if __name__ == "__main__":
    unittest.main()
