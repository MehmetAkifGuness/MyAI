import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main_v170
from boru.architecture import ArchitectureRequest, LLMArchitectAgent
from boru.autonomy import AutonomousDevelopmentCoordinator
from boru.release import build_release
from boru.sandbox.executor import DockerSandboxExecutor
from boru.sandbox.history import TerminalHistory
from boru.sandbox.terminal import SandboxTerminalCoordinator
from boru.tools.edit_workspace import SafeEditWorkspace
from boru.tools.command_models import (
    CommandExecutionResult,
    CommandKind,
    CommandRisk,
    CommandSpec,
)


class FakeTasks:
    def __init__(self):
        self.has_pending = False
        self.calls = []
        self.plan_response = "GÖREV PLANI HAZIRLANDI\nTASK-1"

    def resolve(self, message):
        self.calls.append(message)
        if message.startswith("görev planla:"):
            return self.plan_response
        if message in {"planı çalıştır", "planı devam ettir"}:
            self.has_pending = True
            return "PLANLI GÖREV YÜRÜTME\nDurum: ONAY BEKLİYOR"
        if message == "iptal":
            self.has_pending = False
            return "İptal edildi"
        if message == "görev durumu":
            return "GÖREV DURUMU\nTASK-1 running"
        return "devredildi: " + message


class AutonomousDevelopmentTests(unittest.TestCase):
    def test_goal_creates_plan_and_starts_first_verified_task(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks)

        report = coordinator.resolve("otonom geliştir: calculator.py toplama hatasını düzelt")

        self.assertIn("OTONOM GELİŞTİRME", report)
        self.assertIn("ONAY BEKLİYOR", report)
        self.assertEqual(
            tasks.calls,
            [
                "görev planla: calculator.py toplama hatasını düzelt",
                "planı çalıştır",
            ],
        )
        self.assertTrue(coordinator.has_pending)

    def test_failed_plan_never_starts_execution(self):
        tasks = FakeTasks()
        tasks.plan_response = "Görev planı hazırlanamadı: kapsam geçersiz"
        report = AutonomousDevelopmentCoordinator(tasks).resolve("otonom geliştir: düzelt")

        self.assertIn("PLANLANAMADI", report)
        self.assertEqual(tasks.calls, ["görev planla: düzelt"])
        self.assertFalse(tasks.has_pending)

    def test_approval_and_cancel_are_delegated_to_existing_safe_workflow(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks)
        coordinator.resolve("otonom geliştir: düzelt")

        self.assertEqual(
            coordinator.resolve("kod değişikliğini onayla"),
            "devredildi: kod değişikliğini onayla",
        )
        self.assertIn("İptal edildi", coordinator.resolve("otonom iptal"))
        self.assertFalse(coordinator.has_pending)

    def test_status_continue_limits_and_unknown_commands(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks)
        self.assertIn("GÖREV DURUMU", coordinator.resolve("otonom durum"))
        self.assertIn("ONAY BEKLİYOR", coordinator.resolve("otonom devam et"))
        self.assertIn("Biçimler", coordinator.resolve("otonom uç"))
        oversized = "x" * 4001
        self.assertIn("REDDEDİLDİ", coordinator.resolve("otonom geliştir: " + oversized))


class ExplicitScopeBeyondManifestTests(unittest.TestCase):
    def test_explicit_existing_file_is_loaded_when_bounded_index_omits_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "late_file.py").write_text(
                "def value():\n    return 1\n",
                encoding="utf-8",
            )
            file_index = Mock()
            file_index.list_editable_files.return_value = ()
            selector = Mock()
            model = Mock()
            agent = LLMArchitectAgent(
                chat_model=model,
                file_index=file_index,
                file_selector=selector,
                workspace=SafeEditWorkspace(root),
                creation_validator=Mock(),
                fast_scoped_plans=True,
            )

            plan = agent.plan(
                ArchitectureRequest(
                    "late_file.py icindeki value sonucunu 2 yap",
                    ("late_file.py",),
                )
            )

            self.assertEqual(plan.existing_files, ("late_file.py",))
            selector.select_files.assert_not_called()
            model.generate_structured.assert_not_called()


class AdvancedTerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.executor = Mock()
        self.executor.status.return_value = "SANDBOX DURUMU\nDurum: HAZIR"
        self.executor.execute.side_effect = self._success
        self.history = TerminalHistory(self.root / "history.json")
        self.terminal = SandboxTerminalCoordinator(self.root, self.executor, self.history)

    @staticmethod
    def _success(spec):
        output = "Ran 1 test in 0.001s\n\nOK" if spec.kind is CommandKind.UNITTEST else "OK"
        return CommandExecutionResult(spec, 0, 0.1, output)

    def test_workspace_directory_is_bounded_and_applied_to_container_spec(self):
        self.assertIn("/workspace/pkg", self.terminal.resolve("terminal cd: pkg"))
        self.terminal.resolve("terminal: compileall sample.py")
        spec = self.executor.execute.call_args.args[0]
        self.assertEqual(spec.working_directory, "pkg")
        self.assertEqual(spec.arguments, ("-m", "compileall", "-q", "sample.py"))
        self.assertIn("/workspace/pkg", self.terminal.resolve("terminal pwd"))
        self.assertIn("ÇALIŞTIRILAMADI", self.terminal.resolve("terminal cd: ../outside"))

    def test_environment_dependency_and_canonical_history(self):
        self.terminal.resolve("terminal ortamı")
        self.terminal.resolve("terminal: pip check")
        history = self.terminal.resolve("terminal geçmişi")

        kinds = [call.args[0].kind for call in self.executor.execute.call_args_list]
        self.assertEqual(kinds, [CommandKind.ENVIRONMENT, CommandKind.PIP_CHECK])
        self.assertIn("-m pip check", history)
        self.assertNotIn("terminal:", history)

    def test_quality_pipeline_runs_three_separate_commands_without_shell(self):
        report = self.terminal.resolve("terminal kalite: pkg/sample.py")
        self.assertIn("Aşama: 3/3 geçti", report)
        self.assertEqual(
            [call.args[0].kind for call in self.executor.execute.call_args_list],
            [CommandKind.COMPILEALL, CommandKind.RUFF, CommandKind.MYPY],
        )

    def test_blocked_input_is_not_executed_or_written_to_history(self):
        report = self.terminal.resolve("terminal: python -c __import__('os').system('whoami')")
        self.assertIn("ÇALIŞTIRILAMADI", report)
        self.executor.execute.assert_not_called()
        self.assertIn("Kayıt: 0", self.terminal.resolve("terminal geçmişi"))

    def test_corrupt_or_oversized_history_fails_closed(self):
        path = self.root / "history.json"
        path.write_text('{"version":99,"entries":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sürümü"):
            self.history.render()
        path.write_text("x" * (128 * 1024 + 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "boyut"):
            self.history.render()

    def test_nonzero_quality_stage_fails_whole_pipeline(self):
        def result(spec):
            code = 1 if spec.kind is CommandKind.RUFF else 0
            return CommandExecutionResult(spec, code, 0.1, "lint failed" if code else "OK")

        self.executor.execute.side_effect = result
        report = self.terminal.resolve("terminal kalite: pkg/sample.py")
        self.assertIn("TERMİNAL KALİTE HATTI\nDurum: BAŞARISIZ", report)
        self.assertIn("Aşama: 2/3 geçti", report)

    def test_features_are_exposed_at_their_release_level(self):
        terminal = SandboxTerminalCoordinator(
            self.root,
            self.executor,
            feature_level=0,
        )
        self.assertIn("ÇALIŞTIRILAMADI", terminal.resolve("terminal cd: pkg"))
        terminal = SandboxTerminalCoordinator(
            self.root,
            self.executor,
            feature_level=4,
        )
        self.assertIn("BAŞARILI", terminal.resolve("terminal: pip check"))
        self.assertIn("ÇALIŞTIRILAMADI", terminal.resolve("terminal: compileall pkg"))


class CommandPolicyExtensionTests(unittest.TestCase):
    def test_executor_rejects_forged_environment_and_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = DockerSandboxExecutor(Path(directory), runner=Mock(), docker="docker")
            forged = CommandSpec(
                CommandKind.ENVIRONMENT,
                "python",
                ("-c", "print('forged')"),
                "forged",
                CommandRisk.SAFE,
            )
            with self.assertRaisesRegex(ValueError, "reddeder|boş"):
                executor._canonical_arguments(forged)
            traversal = CommandSpec(
                CommandKind.PIP_CHECK,
                "python",
                ("-m", "pip", "check"),
                "pip check",
                CommandRisk.SAFE,
                "../outside",
            )
            with self.assertRaisesRegex(ValueError, "güvenli"):
                executor._canonical_arguments(traversal)


@unittest.skipUnless(os.environ.get("BORU_RUN_DOCKER_TESTS") == "1", "Opt-in Docker integration")
class LiveAdvancedTerminalTests(unittest.TestCase):
    def test_environment_cwd_compile_and_dependency_check_in_real_container(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pkg").mkdir()
            source = root / "pkg" / "sample.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            terminal = SandboxTerminalCoordinator(root, DockerSandboxExecutor(root))
            self.assertIn("/workspace/pkg", terminal.resolve("terminal cd: pkg"))
            environment = terminal.resolve("terminal ortamı")
            self.assertIn("Durum: BAŞARILI", environment)
            self.assertIn("cwd=/workspace/pkg", environment)
            self.assertIn("Durum: BAŞARILI", terminal.resolve("terminal: compileall sample.py"))
            self.assertIn("Durum: BAŞARILI", terminal.resolve("terminal: pip check"))
            self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 1\n")


class ReleaseV400Tests(unittest.TestCase):
    def test_v400_release_enables_autonomous_and_terminal_features(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V4.0"), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V4.0")
            self.assertTrue(flags["sandbox_terminal_enabled"])
            self.assertTrue(flags["autonomous_development_enabled"])
            self.assertTrue(flags["reliable_tasks_enabled"])
            self.assertEqual(flags["terminal_feature_level"], 9)
            self.assertEqual(flags["autonomy_feature_level"], 0)

    def test_all_intermediate_releases_remain_buildable(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            for version in (
                "V3.1", "V3.2", "V3.3", "V3.4", "V3.5",
                "V3.6", "V3.7", "V3.8", "V3.9", "V4.0",
            ):
                self.assertEqual(build_release(version), "app")
                self.assertEqual(builder.call_args.kwargs["application_version"], version)
                expected_level = 9 if version == "V4.0" else int(version.split(".")[1])
                self.assertEqual(
                    builder.call_args.kwargs["terminal_feature_level"],
                    expected_level,
                )


if __name__ == "__main__":
    unittest.main()
