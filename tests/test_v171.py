import json
import unittest

from boru.architecture import (
    ArchitectureRequest,
    LLMArchitectAgent,
    RuleBasedArchitectureRequestParser,
)
from boru.tools import EditSource, ProjectFileSelection, RuleBasedToolPlanner


class StructuredModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def generate_structured(self, messages, schema):
        del messages, schema
        self.calls += 1
        return json.dumps(self.outputs.pop(0), ensure_ascii=False)


class StaticIndex:
    def list_editable_files(self):
        return (
            "boru/tools/command_parser.py",
            "boru/tools/command_models.py",
            "boru/architecture/models.py",
        )


class RecordingSelector:
    def __init__(self):
        self.available_paths = ()

    def select_files(self, *, request, available_paths):
        del request
        self.available_paths = available_paths
        return ProjectFileSelection(available_paths)


class Workspace:
    def read_edit_source(self, path):
        return EditSource(path, "VALUE = 1\n", "hash")


class CreationValidator:
    def validate_new_text_file(self, relative_path, content):
        del relative_path, content


def plan(existing_files, new_files=()):
    files = [*existing_files, *new_files]
    return {
        "summary": "Güvenli komut türünü mevcut yapıya ekle.",
        "existing_files": list(existing_files),
        "new_files": list(new_files),
        "steps": [{
            "title": "Komut sözleşmesini güncelle",
            "description": "Ayrıştırma ve model kurallarını geriye uyumlu genişlet.",
            "files": files,
        }],
        "risks": ["Geriye uyumluluk"],
        "tests": ["Ayrıştırıcı regresyon testlerini çalıştır"],
        "notes": [],
    }


class V171RegressionTests(unittest.TestCase):
    def test_project_file_listing_uses_deterministic_root_tool(self):
        decision = RuleBasedToolPlanner().plan("Projedeki dosyaları listele")
        self.assertTrue(decision.should_use_tool)
        self.assertEqual(decision.tool_call.tool_name, "list_directory")
        self.assertEqual(decision.tool_call.arguments, {"path": "."})

    def test_architecture_parser_extracts_explicit_file_scope(self):
        request = RuleBasedArchitectureRequestParser().parse(
            "mimari planla: boru/tools/command_parser.py ve "
            "boru/tools/command_models.py içinde yalnızca bu iki dosyayı kapsayan plan hazırla"
        )
        self.assertEqual(
            request.file_scope,
            (
                "boru/tools/command_parser.py",
                "boru/tools/command_models.py",
            ),
        )

    def test_architect_retries_plan_that_exceeds_explicit_scope(self):
        allowed = (
            "boru/tools/command_parser.py",
            "boru/tools/command_models.py",
        )
        model = StructuredModel([
            plan(allowed, ("boru/architecture/models.py",)),
            plan(allowed),
        ])
        selector = RecordingSelector()
        agent = LLMArchitectAgent(
            chat_model=model,
            file_index=StaticIndex(),
            file_selector=selector,
            workspace=Workspace(),
            creation_validator=CreationValidator(),
        )

        result = agent.plan(ArchitectureRequest("güvenli komutu planla", allowed))

        self.assertEqual(model.calls, 2)
        self.assertEqual(selector.available_paths, allowed)
        self.assertEqual(result.existing_files, allowed)
        self.assertEqual(result.new_files, ())


if __name__ == "__main__":
    unittest.main()
