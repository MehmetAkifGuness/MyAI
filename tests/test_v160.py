import json
import unittest

from boru.architecture import (
    ArchitectCoordinator,
    ArchitecturePlan,
    ArchitectureRequest,
    ArchitectureStep,
    JsonArchitecturePlanParser,
    LLMArchitectAgent,
    RuleBasedArchitectureRequestParser,
)
from boru.memory import ConservativeMemoryDecisionGate
from boru.tools import EditSource, ProjectFileSelection


def valid_plan(**overrides) -> str:
    data = {
        "summary": "Komut ayrıştırmayı küçük bir değişiklikle genişlet.",
        "existing_files": ["a.py"],
        "new_files": ["tests/test_a.py"],
        "steps": [
            {
                "title": "Ayrıştırıcıyı güncelle",
                "description": "Mevcut sözleşmeyi koruyarak yeni kuralı ekle.",
                "files": ["a.py", "tests/test_a.py"],
            }
        ],
        "risks": ["Geriye uyumluluk"],
        "tests": ["Yeni kuralı ve geçersiz girdiyi test et"],
        "notes": ["Yeni bağımlılık ekleme"],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class StructuredModel:
    def __init__(self, outputs) -> None:
        self.outputs = list(outputs)
        self.calls = []

    def generate_structured(self, messages, schema):
        self.calls.append((messages, schema))
        return self.outputs.pop(0)


class StaticIndex:
    def list_editable_files(self):
        return ("a.py", "b.py", "tests/existing.py")


class StaticSelector:
    def __init__(self, paths=("a.py",)) -> None:
        self.paths = paths
        self.requests = []

    def select_files(self, *, request, available_paths):
        self.requests.append((request, available_paths))
        return ProjectFileSelection(self.paths)


class RecordingWorkspace:
    def __init__(self) -> None:
        self.reads = []

    def read_edit_source(self, path):
        self.reads.append(path)
        return EditSource(path, "VALUE = 1\n", "hash")


class RecordingCreationValidator:
    def __init__(self, rejected=()) -> None:
        self.rejected = set(rejected)
        self.paths = []

    def validate_new_text_file(self, relative_path, content):
        self.paths.append((relative_path, content))
        if relative_path in self.rejected:
            raise ValueError("unsafe path")


def build_agent(outputs, **overrides):
    parts = {
        "chat_model": StructuredModel(outputs),
        "file_index": StaticIndex(),
        "file_selector": StaticSelector(),
        "workspace": RecordingWorkspace(),
        "creation_validator": RecordingCreationValidator(),
    }
    parts.update(overrides)
    return LLMArchitectAgent(**parts), parts


class ArchitectureParserTests(unittest.TestCase):
    def test_request_parser_is_explicit_and_fail_closed(self) -> None:
        parser = RuleBasedArchitectureRequestParser()
        self.assertEqual(
            parser.parse("mimari planla: retry servisi ekle"),
            ArchitectureRequest("retry servisi ekle"),
        )
        self.assertIsNone(parser.parse("mimari planla"))
        self.assertTrue(parser.is_architecture_intent("mimari planla"))

    def test_json_parser_rejects_extra_fields(self) -> None:
        raw = json.loads(valid_plan())
        raw["command"] = "write file"
        with self.assertRaises(ValueError):
            JsonArchitecturePlanParser().parse(json.dumps(raw))


class ArchitectAgentTests(unittest.TestCase):
    def test_grounds_plan_to_selected_sources_and_validates_new_paths(self) -> None:
        model = StructuredModel([valid_plan()])
        selector = StaticSelector()
        workspace = RecordingWorkspace()
        validator = RecordingCreationValidator()
        agent = LLMArchitectAgent(
            chat_model=model,
            file_index=StaticIndex(),
            file_selector=selector,
            workspace=workspace,
            creation_validator=validator,
        )

        plan = agent.plan(ArchitectureRequest("özelliği ekle"))

        self.assertEqual(plan.existing_files, ("a.py",))
        self.assertEqual(workspace.reads, ["a.py"])
        self.assertEqual(validator.paths, [("tests/test_a.py", "")])
        messages, schema = model.calls[0]
        self.assertIn("<BORU_PROJECT_FILE", messages[1].content)
        self.assertFalse(schema["additionalProperties"])

    def test_rejects_existing_file_outside_selection(self) -> None:
        agent, _ = build_agent(
            [valid_plan(existing_files=["outside.py"], new_files=[], steps=[{
                "title": "Yanlış",
                "description": "Manifest dışı dosya",
                "files": ["outside.py"],
            }])],
            max_attempts=1,
        )
        with self.assertRaisesRegex(ValueError, "manifest dışında"):
            agent.plan(ArchitectureRequest("görev"))

    def test_loads_manifested_additional_source_then_replans(self) -> None:
        expanded = valid_plan(
            existing_files=["a.py", "b.py"],
            new_files=[],
            steps=[{
                "title": "İki dosyayı güncelle",
                "description": "Bağımlılığı koru",
                "files": ["a.py", "b.py"],
            }],
        )
        model = StructuredModel([expanded, expanded])
        workspace = RecordingWorkspace()
        agent, _ = build_agent(
            [expanded],
            chat_model=model,
            workspace=workspace,
        )
        plan = agent.plan(ArchitectureRequest("görev"))
        self.assertEqual(plan.existing_files, ("a.py", "b.py"))
        self.assertEqual(workspace.reads, ["a.py", "b.py"])
        self.assertEqual(len(model.calls), 2)

    def test_normalizes_manifested_file_misclassified_as_new(self) -> None:
        misclassified = valid_plan(
            existing_files=[],
            new_files=["a.py"],
            steps=[{
                "title": "Dosyayı güncelle",
                "description": "Mevcut davranışı koru",
                "files": ["a.py"],
            }],
        )
        agent, _ = build_agent([misclassified])
        plan = agent.plan(ArchitectureRequest("görev"))
        self.assertEqual(plan.existing_files, ("a.py",))
        self.assertEqual(plan.new_files, ())

    def test_rejects_unsafe_new_file(self) -> None:
        validator = RecordingCreationValidator({"tests/test_a.py"})
        agent, _ = build_agent(
            [valid_plan()],
            creation_validator=validator,
            max_attempts=1,
        )
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            agent.plan(ArchitectureRequest("görev"))

    def test_repairs_invalid_structured_output(self) -> None:
        model = StructuredModel(["{}", valid_plan()])
        agent, _ = build_agent([valid_plan()], chat_model=model)
        plan = agent.plan(ArchitectureRequest("görev"))
        self.assertEqual(plan.summary, "Komut ayrıştırmayı küçük bir değişiklikle genişlet.")
        self.assertEqual(len(model.calls), 2)
        self.assertIn("DOĞRULAMA HATASI", model.calls[1][0][1].content)


class StaticPlanner:
    def plan(self, request):
        return ArchitecturePlan(
            summary=f"Plan: {request.task}",
            existing_files=("a.py",),
            new_files=(),
            steps=(ArchitectureStep("İncele", "Davranışı koru", ("a.py",)),),
            risks=("API değişimi",),
            tests=("Regresyon",),
            notes=(),
        )


class ArchitectCoordinatorTests(unittest.TestCase):
    def test_renders_read_only_plan(self) -> None:
        coordinator = ArchitectCoordinator(
            RuleBasedArchitectureRequestParser(),
            StaticPlanner(),
        )
        response = coordinator.resolve("mimari planla: özelliği ekle")
        self.assertIn("MİMARİ PLAN", response or "")
        self.assertIn("Salt-okunur analiz tamamlandı", response or "")

    def test_memory_gate_rejects_architecture_request(self) -> None:
        self.assertFalse(
            ConservativeMemoryDecisionGate().should_evaluate(
                "mimari planla: kullanıcı servisini yeniden düzenle"
            )
        )


if __name__ == "__main__":
    unittest.main()
