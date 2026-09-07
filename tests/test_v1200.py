import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.agent import ReadOnlyToolAgent
from boru.code_index import (
    CodeSearchTool,
    RelatedCodeTool,
    SafeCodeIndex,
    SafeCodeRelationshipIndex,
)
from boru.release import build_release
from boru.config import AppSettings
from boru.tools import (
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
)


class FinalModel:
    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def generate_structured(self, messages, schema):
        self.prompts.append(messages)
        return json.dumps(
            {
                "action": "final",
                "tool_name": "",
                "arguments": {},
                "answer": self.answer,
                "evidence": [],
                "reason": "Kanıtlar yeterli.",
            }
        )

    def generate(self, messages):
        return self.answer


class VerificationModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def generate_structured(self, messages, schema):
        return json.dumps(self.outputs.pop(0), ensure_ascii=False)

    def generate(self, messages):
        raise RuntimeError("Doğrulama testi serbest sentez kullanmamalıdır.")


class WiringModel(FinalModel):
    def __init__(self, *args, **kwargs):
        super().__init__(
            "ReadOnlyToolAgent runtime.py içindedir. Final yanıtı AgentReportRenderer "
            "üzerinden başarılı ve kullanılabilir kanıt varlığı ile içerik yeterliliğini "
            "doğrulayarak kabul eder; kanıt yoksa final raporu üretmez."
        )


class Ui:
    def __init__(self, assistant, title, startup_message):
        self.assistant = assistant
        self.title = title
        self.startup_message = startup_message


class UnusedSandbox:
    def __init__(self, root, image):
        pass


class RelationshipIndexTests(unittest.TestCase):
    def _project(self, root):
        package = root / "pkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "source.py").write_text(
            "from pkg.reporting import Reporter\n"
            "from .helper import Helper\n"
            "class Service:\n"
            "    def run(self):\n"
            "        reporter = Reporter()\n"
            "        return reporter.render_final()\n",
            encoding="utf-8",
        )
        (package / "reporting.py").write_text(
            "class Reporter:\n    def render_final(self):\n        return 'done'\n",
            encoding="utf-8",
        )
        (package / "helper.py").write_text(
            "class Helper:\n    def assist(self):\n        return None\n",
            encoding="utf-8",
        )

    def test_resolves_absolute_and_relative_imports_and_ranks_called_method(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            related = SafeCodeRelationshipIndex(root).related_files(
                "pkg/source.py",
                "final yanıt",
            )

            self.assertEqual(related[0].path, "pkg/reporting.py")
            self.assertIn("render_final", related[0].matched_calls)
            self.assertEqual({item.path for item in related}, {"pkg/reporting.py", "pkg/helper.py"})

    def test_related_tool_returns_grounded_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            tool = RelatedCodeTool(SafeCodeRelationshipIndex(root))
            result = tool.execute(
                {"path": "pkg/source.py", "query": "final", "max_results": 2}
            )

            self.assertTrue(result.success)
            self.assertIn("pkg/reporting.py", result.content)
            self.assertEqual(result.metadata["paths"][0], "pkg/reporting.py")

    def test_turkish_query_terms_do_not_fragment_relationship_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "runtime.py").write_text(
                "from pkg.reporting import AgentReportRenderer\n"
                "from pkg.final_synthesis import GroundedFinalSynthesizer\n"
                "class ReadOnlyToolAgent:\n"
                "    def finish(self, action, observations, objective):\n"
                "        AgentReportRenderer().usable_observations(observations)\n"
                "        return AgentReportRenderer().render_final(action, observations, objective)\n",
                encoding="utf-8",
            )
            (package / "reporting.py").write_text(
                "class AgentReportRenderer:\n"
                "    def usable_observations(self, value): return value\n"
                "    def render_final(self, action, observations, objective): return None\n",
                encoding="utf-8",
            )
            (package / "final_synthesis.py").write_text(
                "class GroundedFinalSynthesizer:\n"
                "    def synthesize(self):\n"
                "        return 'kanıta dayalı final yanıtı üret'\n",
                encoding="utf-8",
            )

            related = SafeCodeRelationshipIndex(root).related_files(
                "pkg/runtime.py",
                "ReadOnlyToolAgent kanıtsız final yanıtını nasıl engelliyor?",
            )

            self.assertEqual(related[0].path, "pkg/reporting.py")


class DeepEvidenceAgentTests(unittest.TestCase):
    def test_bootstrap_reads_ranked_related_source_before_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            RelationshipIndexTests()._project(root)
            workspace = ReadOnlyWorkspace(root)
            search_index = SafeCodeIndex(root)
            registry = ToolRegistry(
                [
                    ReadFileTool(workspace),
                    CodeSearchTool(search_index),
                    RelatedCodeTool(SafeCodeRelationshipIndex(root)),
                ]
            )
            executor = ToolExecutor(
                registry,
                RiskBasedToolPolicy((ToolRisk.SAFE, ToolRisk.READ_ONLY)),
            )
            answer = (
                "Service pkg/source.py içindedir. run metodu Reporter nesnesini oluşturur "
                "ve pkg/reporting.py içindeki render_final metodunu çağırarak sonucu döndürür."
            )
            model = FinalModel(answer)
            report = ReadOnlyToolAgent(model, registry, executor).run(
                "Service hangi dosyada ve final yanıtı nasıl üretiyor?"
            )

            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn("[T4] read_file — pkg/reporting.py", report)
            self.assertIn("pkg/reporting.py", model.prompts[0][1].content)

    def test_corrects_reversed_guard_condition_before_reporting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guard.py").write_text(
                "class GuardService:\n"
                "    def render_final(self, successful):\n"
                "        if not successful:\n"
                "            return None\n"
                "        return 'ok'\n",
                encoding="utf-8",
            )
            workspace = ReadOnlyWorkspace(root)
            index = SafeCodeIndex(root)
            registry = ToolRegistry(
                [ReadFileTool(workspace), CodeSearchTool(index)]
            )
            executor = ToolExecutor(
                registry,
                RiskBasedToolPolicy((ToolRisk.SAFE, ToolRisk.READ_ONLY)),
            )
            wrong = (
                "GuardService guard.py içindedir. successful doğru olduğunda render_final "
                "None döndürerek final yanıtını engeller ve sonuç üretimini durdurur."
            )
            corrected = (
                "GuardService guard.py içindedir. render_final, successful değeri yanlış veya "
                "boş olduğunda None döndürerek kanıtsız finali engeller; değer doğru olduğunda "
                "ise ok sonucunu üretir."
            )
            model = VerificationModel(
                [
                    {
                        "action": "final",
                        "tool_name": "",
                        "arguments": {},
                        "answer": wrong,
                        "evidence": [],
                        "reason": "test",
                    },
                    {
                        "supported": False,
                        "corrected_answer": corrected,
                        "reason": "Koşul ters yorumlanmış.",
                    },
                ]
            )
            report = ReadOnlyToolAgent(model, registry, executor).run(
                "GuardService kanıtsız final yanıtını nasıl engelliyor?"
            )

            self.assertIn(corrected, report)
            self.assertNotIn(wrong, report)


class ReleaseV120Tests(unittest.TestCase):
    def test_v120_release_enables_deep_code_index(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V1.2"), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V1.2")
            self.assertTrue(flags["general_agent_enabled"])
            self.assertTrue(flags["deep_code_index_enabled"])

    def test_release_collects_cross_file_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "boru" / "agent"
            package.mkdir(parents=True)
            (root / "boru" / "__init__.py").write_text("", encoding="utf-8")
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "runtime.py").write_text(
                "from boru.agent.reporting import AgentReportRenderer\n"
                "class ReadOnlyToolAgent:\n"
                "    def finish(self):\n"
                "        return AgentReportRenderer().render_final()\n",
                encoding="utf-8",
            )
            (package / "reporting.py").write_text(
                "class AgentReportRenderer:\n"
                "    def render_final(self):\n"
                "        return 'grounded'\n",
                encoding="utf-8",
            )
            settings = AppSettings(memory_auto_capture=False, memory_semantic_enabled=False)
            with patch.object(main_v170, "__file__", str(root / "main_v170.py")), \
                 patch.object(main_v170.AppSettings, "from_env", return_value=settings), \
                 patch.object(main_v170, "ChatAppUI", Ui), \
                 patch.object(main_v170, "OllamaChatModel", WiringModel), \
                 patch.object(main_v170, "ModelWarmupService"), \
                 patch.object(main_v170, "DockerSandboxExecutor", UnusedSandbox):
                app = build_release("V1.2")

            report = app.assistant.reply(
                "ReadOnlyToolAgent hangi dosyada ve final yanıtı nasıl doğruluyor?"
            )
            self.assertIn("Durum: TAMAMLANDI", report)
            self.assertIn("read_file — boru/agent/reporting.py", report)
            self.assertIn("V1.2", app.title)


if __name__ == "__main__":
    unittest.main()
