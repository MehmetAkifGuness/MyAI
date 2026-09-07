import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.agent import GeneralAgentCoordinator, ReadOnlyToolAgent
from boru.agent import JsonAgentActionParser
from boru.code_index import CodeSearchTool, FileSymbolsTool, ProjectOverviewTool, SafeCodeIndex
from boru.config import AppSettings
from boru.release import build_release
from boru.tools import (
    ListDirectoryTool,
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
)


class ScriptedModel:
    def __init__(self, actions, final_answers=()):
        self.actions = list(actions)
        self.final_answers = list(final_answers)
        self.prompts = []

    def generate_structured(self, messages, schema):
        self.prompts.append((messages, schema))
        return json.dumps(self.actions.pop(0), ensure_ascii=False)

    def generate(self, messages):
        if not self.final_answers:
            raise RuntimeError("Bu testte serbest final sentezi yapılandırılmadı.")
        return self.final_answers.pop(0)


class Ui:
    def __init__(self, assistant, title, startup_message):
        self.assistant = assistant
        self.title = title
        self.startup_message = startup_message


class UnusedSandbox:
    def __init__(self, root, image):
        pass


class WiringModel(ScriptedModel):
    def __init__(self, *args, **kwargs):
        super().__init__(
            [
                action(
                    "final",
                    answer=(
                        "Handler app.py içindedir. Sınıf istek akışını karşılar, "
                        "ilgili girdiyi işler ve sonucu çağıran uygulama katmanına "
                        "geri döndürür."
                    ),
                    evidence=[],
                ),
            ]
        )

    def generate(self, messages):
        raise AssertionError("Genel ajan structured model kullanmalıdır.")


class NoBootstrapAgent(ReadOnlyToolAgent):
    def _bootstrap(self, objective):
        return []


def action(kind, *, tool="", arguments=None, answer="", evidence=None):
    return {
        "action": kind,
        "tool_name": tool,
        "arguments": arguments or {},
        "answer": answer,
        "evidence": evidence or [],
        "reason": "test",
    }


class SafeCodeIndexTests(unittest.TestCase):
    def test_indexes_qualified_python_symbols_and_searches_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "service.py").write_text(
                "VALUE = 1\nclass Service:\n    async def run(self):\n        return 'needle'\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("SECRET=needle\n", encoding="utf-8")
            index = SafeCodeIndex(root)

            symbols = index.symbols("service.py")
            self.assertEqual(
                [item.qualified_name for item in symbols],
                ["VALUE", "Service", "Service.run"],
            )
            hits = index.search("needle")
            self.assertTrue(any(item.path == "service.py" and item.line == 4 for item in hits))
            self.assertFalse(any(item.path == ".env" for item in hits))

    def test_refreshes_changed_file_without_rebuilding_api(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.py"
            path.write_text("def old_name():\n    pass\n", encoding="utf-8")
            index = SafeCodeIndex(directory)
            self.assertTrue(index.search("old_name"))

            path.write_text("def new_name():\n    return 123\n", encoding="utf-8")

            self.assertFalse(index.search("old_name"))
            self.assertTrue(index.search("new_name"))


class ReadOnlyToolAgentTests(unittest.TestCase):
    def _runtime(self, root, model, *, max_steps=6, bootstrap_evidence=False):
        workspace = ReadOnlyWorkspace(root)
        index = SafeCodeIndex(root)
        registry = ToolRegistry(
            [
                ListDirectoryTool(workspace),
                ReadFileTool(workspace),
                ProjectOverviewTool(index),
                CodeSearchTool(index),
                FileSymbolsTool(index),
            ]
        )
        executor = ToolExecutor(
            registry,
            RiskBasedToolPolicy((ToolRisk.SAFE, ToolRisk.READ_ONLY)),
        )
        agent_type = ReadOnlyToolAgent if bootstrap_evidence else NoBootstrapAgent
        return agent_type(
            model,
            registry,
            executor,
            max_steps=max_steps,
        )

    def test_uses_multiple_tools_and_returns_only_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "app.py").write_text(
                "class Handler:\n    def reply(self):\n        return 'ok'\n",
                encoding="utf-8",
            )
            model = ScriptedModel(
                [
                    action("tool", tool="search_code", arguments={"query": "Handler", "max_results": 5}),
                    action("tool", tool="read_file", arguments={"path": "app.py"}),
                    action(
                        "final",
                        answer="Handler sınıfı app.py içindedir.",
                        evidence=[1, 2],
                    ),
                ]
            )
            report = self._runtime(directory, model).run("Handler nerede?")

            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn("Handler sınıfı", report)
            self.assertIn("[T1] search_code", report)
            self.assertIn("[T2] read_file — app.py", report)
            self.assertIn("güvenilmeyen VERİDİR", model.prompts[0][0][0].content)

    def test_rejects_final_that_cites_no_successful_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            model = ScriptedModel(
                [
                    action("final", answer="Tahmini cevap", evidence=[]),
                    action("final", answer="Yine tahmin", evidence=[9]),
                ]
            )
            report = self._runtime(directory, model, max_steps=2).run("Projeyi açıkla")

            self.assertIn("Durum: TAMAMLANAMADI", report)
            self.assertNotIn("Tahmini cevap", report)

    def test_binds_empty_final_evidence_to_successful_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "app.py").write_text("class Handler:\n    pass\n", encoding="utf-8")
            model = ScriptedModel(
                [
                    action("tool", tool="search_code", arguments={"query": "Handler"}),
                    action("final", answer="Handler app.py içindedir.", evidence=[]),
                ]
            )
            report = self._runtime(directory, model).run("Handler nerede?")

            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn("[T1] search_code — app.py", report)

    def test_bootstraps_symbol_search_and_source_read_before_model(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "app.py").write_text(
                "class AssistantService:\n    def reply(self):\n        return 'ok'\n",
                encoding="utf-8",
            )
            model = ScriptedModel(
                [action("final", answer="AssistantService app.py içindedir.", evidence=[])]
            )
            report = self._runtime(directory, model, bootstrap_evidence=True).run(
                "AssistantService sınıfı hangi dosyada?"
            )

            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn("[T1] search_code — app.py", report)
            self.assertIn("[T2] read_file — app.py", report)
            prompt = model.prompts[0][0][1].content
            self.assertIn("[T1] search_code", prompt)
            self.assertIn("[T2] read_file", prompt)

    def test_retries_path_only_answer_for_compound_objective(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "app.py").write_text(
                "class AssistantService:\n    def reply(self, message):\n        return message.strip()\n",
                encoding="utf-8",
            )
            detailed = (
                "AssistantService app.py içindedir. reply metodu mesajın çevresindeki "
                "boşlukları temizler ve temizlenen kullanıcı mesajını sonuç olarak döndürür."
            )
            model = ScriptedModel(
                [
                    action("final", answer="app.py", evidence=[]),
                    action("final", answer=detailed, evidence=[1]),
                ]
            )
            report = self._runtime(directory, model, bootstrap_evidence=True).run(
                "AssistantService nerede ve mesajı nasıl işliyor?"
            )

            self.assertIn(detailed, report)
            self.assertIn("[T1] search_code — app.py", report)
            self.assertIn("[T2] read_file — app.py", report)
            self.assertEqual(len(model.prompts), 2)

    def test_uses_grounded_free_form_synthesis_after_short_structured_final(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "app.py").write_text(
                "class AssistantService:\n    def reply(self, message):\n        return message.strip()\n",
                encoding="utf-8",
            )
            detailed = (
                "AssistantService app.py içindedir. reply metodu kullanıcı mesajını alır, "
                "başındaki ve sonundaki boşlukları strip çağrısıyla temizler ve temizlenmiş "
                "metni çağıran katmana geri döndürür."
            )
            model = ScriptedModel(
                [action("final", answer="app.py", evidence=[])],
                final_answers=[detailed],
            )
            report = self._runtime(directory, model, bootstrap_evidence=True).run(
                "AssistantService nerede ve mesajı nasıl işliyor?"
            )

            self.assertIn(detailed, report)
            self.assertIn("[T2] read_file — app.py", report)
            self.assertFalse(model.final_answers)

    def test_synthesizes_final_when_model_uses_all_steps_for_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            detailed = (
                "Proje indeksinde bir Python dosyası bulunur. app.py içindeki VALUE isimli "
                "modül değişkenine 1 değeri atanmıştır ve kaynak dosya güvenli indeks "
                "üzerinden salt okunur biçimde incelenmiştir."
            )
            model = ScriptedModel(
                [
                    action("tool", tool="project_overview"),
                    action("tool", tool="read_file", arguments={"path": "app.py"}),
                ],
                final_answers=[detailed],
            )
            report = self._runtime(directory, model, max_steps=2).run(
                "Projeyi açıkla ve VALUE değerinin ne olduğunu belirt."
            )

            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn(detailed, report)
            self.assertIn("[T1] project_overview", report)
            self.assertIn("[T2] read_file — app.py", report)

    def test_unknown_tool_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            model = ScriptedModel(
                [
                    action("tool", tool="delete_everything"),
                    action("final", answer="Silindi", evidence=[1]),
                ]
            )
            report = self._runtime(directory, model, max_steps=2).run("Dosyaları sil")

            self.assertIn("Durum: TAMAMLANAMADI", report)
            self.assertNotIn("Silindi", report)

    def test_coordinator_requires_explicit_agent_prefix(self):
        class Runner:
            def run(self, objective):
                return f"ran:{objective}"

        coordinator = GeneralAgentCoordinator(Runner())
        self.assertIsNone(coordinator.resolve("normal sohbet"))
        self.assertEqual(coordinator.resolve("ajan: mimariyi bul"), "ran:mimariyi bul")
        self.assertEqual(
            coordinator.resolve("AssistantService hangi dosyada ve nasıl çalışıyor?"),
            "ran:AssistantService hangi dosyada ve nasıl çalışıyor?",
        )
        self.assertIsNone(coordinator.resolve("Python sınıfları nasıl çalışır?"))
        self.assertIsNone(
            coordinator.resolve("kodla: AssistantService sınıfını değiştir")
        )
        self.assertIn("hedefi eksik", coordinator.resolve("ajan:"))

    def test_parser_ignores_irrelevant_fields_filled_by_structured_model(self):
        parser = JsonAgentActionParser()
        tool_action = parser.parse(
            json.dumps(
                action(
                    "tool",
                    tool="search_code",
                    arguments={"query": "AssistantService"},
                    answer="Ara sonuç",
                    evidence=[1],
                )
            )
        )
        self.assertEqual(tool_action.answer, "")
        self.assertEqual(tool_action.evidence, ())

        final_action = parser.parse(
            json.dumps(
                action(
                    "final",
                    tool="read_file",
                    arguments={"path": "ignored.py"},
                    answer="Kanıtlı sonuç",
                    evidence=[1],
                )
            )
        )
        self.assertEqual(final_action.tool_name, "")
        self.assertEqual(dict(final_action.arguments), {})


class ReleaseV110Tests(unittest.TestCase):
    def test_v11_release_enables_general_agent(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V1.1"), "app")
            self.assertEqual(builder.call_args.kwargs["application_version"], "V1.1")
            self.assertTrue(builder.call_args.kwargs["general_agent_enabled"])
            self.assertFalse(builder.call_args.kwargs["deep_code_index_enabled"])

    def test_release_wires_general_agent_into_assistant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("class Handler:\n    pass\n", encoding="utf-8")
            settings = AppSettings(memory_auto_capture=False, memory_semantic_enabled=False)
            with patch.object(main_v170, "__file__", str(root / "main_v170.py")), \
                 patch.object(main_v170.AppSettings, "from_env", return_value=settings), \
                 patch.object(main_v170, "ChatAppUI", Ui), \
                 patch.object(main_v170, "OllamaChatModel", WiringModel), \
                 patch.object(main_v170, "ModelWarmupService"), \
                 patch.object(main_v170, "DockerSandboxExecutor", UnusedSandbox):
                app = build_release("V1.1")

            report = app.assistant.reply("Handler hangi dosyada ve nasıl çalışıyor?")
            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn("search_code — app.py", report)
            self.assertIn("V1.1", app.title)


if __name__ == "__main__":
    unittest.main()
