import os
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

import main_v170
from boru.config import AppSettings
from boru.release import build_release
from boru.tools.command_executor import BoundedCommandExecutor
from boru.sandbox import DockerSandboxExecutor


class Ui:
    def __init__(self, assistant, title, startup_message):
        self.assistant = assistant
        self.title = title
        self.startup_message = startup_message


class NoModel:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, messages):
        raise AssertionError("Kontrol komutları sohbet modeline düşmemeli.")

    def generate_structured(self, *args, **kwargs):
        raise AssertionError("Bu senaryo deterministik olmalı.")


class TestOnlyExecutor(BoundedCommandExecutor):
    def __init__(self, root, image):
        super().__init__(root)

    def status(self):
        return "SANDBOX DURUMU\nDurum: TEST DOUBLE"

    def execute(self, spec):
        return super().execute(replace(spec, arguments=("-B", *spec.arguments)))


class ReleaseWorkflowTests(unittest.TestCase):
    executor_class = TestOnlyExecutor

    def test_release_wires_all_features_and_runs_confirmed_improvement(self):
        executor_patch = patch.object(main_v170, "DockerSandboxExecutor", self.executor_class)
        executor_patch.start()
        self.addCleanup(executor_patch.stop)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests/__init__.py").write_text("", encoding="utf-8")
            (root / "tests/test_a.py").write_text(
                "import unittest\nimport a\nclass Values(unittest.TestCase):\n"
                "    def test_value(self):\n        self.assertEqual(a.VALUE, 2)\n", encoding="utf-8")
            with patch.object(main_v170, "__file__", str(root / "main_v170.py")), \
                 patch.object(main_v170.AppSettings, "from_env", return_value=AppSettings(memory_auto_capture=False, memory_semantic_enabled=False)), \
                 patch.object(main_v170, "ChatAppUI", Ui), \
                 patch.object(main_v170, "OllamaChatModel", NoModel), \
                 patch.object(main_v170, "ModelWarmupService"), \
                 patch.object(main_v170, "DockerSandboxExecutor", self.executor_class):
                app = build_release("V1.0")
            self.assertIn("V1.0", app.title)
            self.assertIn("SANDBOX DURUMU", app.assistant.reply("sandbox durumu"))
            report = app.assistant.reply("kendini değerlendir: a.py")
            self.assertIn("BAŞARISIZ", report)
            preview = app.assistant.reply("iyileştir: a.py | a.py içinde VALUE değerini yalnızca bu dosyada 2 yap")
            self.assertIn("iyileştirmeyi onayla", preview)
            self.assertEqual((root / "a.py").read_text(), "VALUE = 1\n")
            self.assertIn("onay bekliyor", app.assistant.reply("onayla"))
            applied = app.assistant.reply("iyileştirmeyi onayla")
            self.assertIn("değişikliği uygulandı", applied)
            self.assertEqual((root / "a.py").read_text(), "VALUE = 2\n")
            self.assertIn("Durum: GEÇTİ", app.assistant.reply("kendini değerlendir: a.py"))
            app.assistant.reply("iyileştirmeyi geri al")
            undone = app.assistant.reply("iyileştirme geri almayı onayla")
            self.assertIn("geri alındı", undone)
            self.assertEqual((root / "a.py").read_text(), "VALUE = 1\n")

    def test_milestone_flags(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            for version in ("V0.27", "V0.28", "V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9"):
                self.assertEqual(build_release(version), "app")
                flags = builder.call_args.kwargs
                self.assertTrue(flags["sandbox_enabled"])
                self.assertEqual(flags["evaluation_enabled"], version != "V0.27")
                self.assertEqual(flags["improvement_enabled"], version in {"V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["general_agent_enabled"], version in {"V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["deep_code_index_enabled"], version in {"V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["natural_change_enabled"], version in {"V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["goal_driven_change_enabled"], version in {"V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["impact_analysis_enabled"], version in {"V1.5", "V1.6", "V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["runtime_test_agent_enabled"], version in {"V1.6", "V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["runtime_repair_enabled"], version in {"V1.7", "V1.8", "V1.9"})
                self.assertEqual(flags["batch_runtime_repair_enabled"], version in {"V1.8", "V1.9"})
                self.assertEqual(flags["planned_task_execution_enabled"], version == "V1.9")


@unittest.skipUnless(os.getenv("BORU_RUN_DOCKER_TESTS") == "1", "Docker canlı akış testi isteğe bağlı")
class LiveReleaseWorkflowTests(ReleaseWorkflowTests):
    executor_class = DockerSandboxExecutor


if __name__ == "__main__":
    unittest.main()
