import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from boru.persistence import JsonFileWriteError
from boru.release import build_release
from boru.sandbox.terminal import SandboxTerminalCoordinator
from boru.tasks import (
    JsonTaskCheckpointRepository, TaskCheckpoint, TaskItem, TaskPlan, TaskStatus,
    TaskPlanCoordinator, RuleBasedTaskCommandParser, TaskSourceFingerprintGuard,
)
from boru.tasks.checkpoint_storage import CheckpointStorage
from boru.tasks.managed_checkpoint import ManagedTaskCheckpointRepository
from boru.tasks.reliable_state import ReliableTaskPlanState
from boru.tasks.reliable_coordinator import ReliableTaskCoordinator
from boru.tasks.workflow_guard import GuardedTaskWorkflow
from boru.tools.command_models import CommandExecutionResult


def make_plan():
    return TaskPlan("Değerleri düzelt", "İki görev", (
        TaskItem("TASK-1", "İlk", "FIRST değerini 2 yap", ("first.py",)),
        TaskItem("TASK-2", "İkinci", "SECOND değerini 3 yap", ("second.py",), ("TASK-1",)),
    ))


class TaskFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "checkpoint.json"
        (self.root / "first.py").write_text("FIRST = 1\n", encoding="utf-8")
        (self.root / "second.py").write_text("SECOND = 1\n", encoding="utf-8")

    def repository(self):
        repository = ManagedTaskCheckpointRepository(self.path)
        self.addCleanup(repository.close)
        return repository

    def state(self, repository=None, clock=lambda: 1000.0):
        return ReliableTaskPlanState(
            repository or self.repository(), TaskSourceFingerprintGuard(self.root), clock=clock,
        )


class ManagedCheckpointTests(TaskFixture):
    def test_unknown_nested_fields_block_migration_without_data_loss(self):
        legacy = JsonTaskCheckpointRepository(self.path)
        legacy.save(TaskCheckpoint(make_plan()))
        document = json.loads(self.path.read_text(encoding="utf-8"))
        document["plan"]["tasks"][0]["future_setting"] = "preserve me"
        self.path.write_text(json.dumps(document), encoding="utf-8")
        before = self.path.read_bytes()
        repository = self.repository()
        self.assertIsNone(repository.load().plan)
        self.assertIn("CHECKPOINT_INVALID", repository.status())
        self.assertEqual(before, self.path.read_bytes())

    def test_v2_migration_keeps_fingerprints_and_original_backup(self):
        legacy = JsonTaskCheckpointRepository(self.path)
        original = TaskCheckpoint(make_plan())
        legacy.save(original)
        before = json.loads(self.path.read_text(encoding="utf-8"))
        repository = self.repository()
        self.assertEqual(repository.load(), original)
        self.assertEqual(repository.last_migrated_from, 2)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], 3)
        self.assertEqual(json.loads(repository._disk.backup.read_text(encoding="utf-8")), before)

    def test_corrupt_checkpoint_blocks_writes_and_restore_requires_proposal(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        repository.close()
        self.path.write_text("{broken", encoding="utf-8")
        reopened = self.repository()
        self.assertIsNone(reopened.load().plan)
        with self.assertRaisesRegex(RuntimeError, "CHECKPOINT_INVALID"):
            reopened.save(TaskCheckpoint(None))
        with self.assertRaises(ValueError):
            reopened.restore()
        self.assertIn("onayla", reopened.prepare_restore())
        preserved = reopened.restore()
        self.assertEqual(preserved.read_text(encoding="utf-8"), "{broken")
        self.assertEqual(reopened.load().plan, make_plan())

    def test_backup_change_invalidates_restore_approval(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        repository.prepare_restore()
        repository._disk.backup.write_text("{}", encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "değişti"):
            repository.restore()
        self.assertEqual(self.path.read_bytes(), before)

    def test_future_checkpoint_is_not_downgraded_by_restore(self):
        repository = self.repository()
        self.state(repository).replace_plan(make_plan())
        repository.close()
        self.path.write_text('{"version":99}', encoding="utf-8")
        reopened = self.repository()
        reopened.load()
        with self.assertRaisesRegex(ValueError, "düşürülemez"):
            reopened.prepare_restore()
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"version":99}')

    def test_project_lock_blocks_second_repository_and_releases_on_close(self):
        repository = self.repository()
        with self.assertRaisesRegex(RuntimeError, "PROJECT_LOCKED"):
            self.repository()
        repository.close()
        self.repository().load()

    def test_external_checkpoint_change_blocks_stale_writer(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        self.path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "CHECKPOINT_CHANGED"):
            state.start("TASK-1")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{}")

    def test_failed_commit_rolls_back_memory_and_keeps_previous_checkpoint(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        original = self.path.read_bytes()
        write = repository._disk.write

        def fail_primary(path, document):
            if path == self.path:
                raise JsonFileWriteError("disk full")
            write(path, document)

        with patch.object(repository._disk, "write", side_effect=fail_primary):
            with self.assertRaises(RuntimeError):
                state.start("TASK-1")
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.PENDING)
        self.assertEqual(state._execution.attempts, ())
        self.assertEqual(self.path.read_bytes(), original)

    def test_replaced_plan_is_archived_and_completed_plan_can_be_archived(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        state.replace_plan(make_plan())
        self.assertIn("Kayıt: 1", repository.list_archives())
        with self.assertRaisesRegex(ValueError, "tamamlanmış"):
            state.archive()
        for task_id in ("TASK-1", "TASK-2"):
            state.start(task_id)
            state.transition(task_id, TaskStatus.COMPLETED)
        identifier = state.archive()
        self.assertIsNone(state.get_plan())
        self.assertIn(identifier, repository.list_archives())


class ReliableExecutionTests(TaskFixture):
    def test_restore_uses_exclusive_confirmation_and_never_edits_sources(self):
        from boru.tools.operation_router import ExclusiveOperationCoordinator

        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        coordinator = Mock(has_pending=False)
        admin = ReliableTaskCoordinator(coordinator, state, repository)
        other = Mock(has_pending=False)
        router = ExclusiveOperationCoordinator((admin, other))
        before = self.path.read_bytes()
        self.assertIn("ÖNERİSİ", router.resolve("checkpoint geri yükle"))
        self.assertIn("onay bekliyor", router.resolve("onayla"))
        self.assertEqual(before, self.path.read_bytes())
        self.assertTrue(admin.has_pending)
        self.assertIn("geri yüklendi", router.resolve("checkpoint geri yüklemeyi onayla"))
        self.assertFalse(admin.has_pending)
        self.assertEqual((self.root / "first.py").read_text(encoding="utf-8"), "FIRST = 1\n")
        other.resolve.assert_not_called()

    def test_successful_two_task_workflow_updates_only_approved_sources(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        workflow = Mock(has_pending=False)
        approved = []

        def respond(message):
            if message.startswith("ajan görevi:"):
                workflow.has_pending = True
                return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"
            if message == "kod değişikliğini onayla":
                filename, content = ("first.py", "FIRST = 2\n") if not approved else ("second.py", "SECOND = 3\n")
                (self.root / filename).write_text(content, encoding="utf-8")
                approved.append(filename)
                workflow.has_pending = False
                return "ORKESTRATÖR RAPORU\nGenel durum: TAMAMLANDI"
            return "Onay bekliyor"

        workflow.resolve.side_effect = respond
        coordinator = TaskPlanCoordinator(
            parser=RuleBasedTaskCommandParser(), planner=Mock(),
            workflow=GuardedTaskWorkflow(workflow, state), state=state, planned_execution_enabled=True,
        )
        admin = ReliableTaskCoordinator(coordinator, state, repository)
        self.assertIn("ONAY BEKLİYOR", admin.resolve("planı çalıştır"))
        self.assertEqual(approved, [])
        self.assertIn("SONRAKİ ADIM", admin.resolve("kod değişikliğini onayla"))
        self.assertEqual(approved, ["first.py"])
        self.assertIn("Durum: TAMAMLANDI", admin.resolve("kod değişikliğini onayla"))
        self.assertEqual(approved, ["first.py", "second.py"])
        self.assertIn("Durum: GEÇERLİ", state.health())
        repository.close()
        restored = self.state()
        self.assertTrue(all(task.status is TaskStatus.COMPLETED for task in restored.get_plan().tasks))
        self.assertIn("Durum: GEÇERLİ", restored.health())

    def test_attempt_budget_survives_restart_and_reset(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        for _ in range(3):
            state.start("TASK-1")
            state.transition("TASK-1", TaskStatus.FAILED)
            state.reset("TASK-1")
        repository.close()
        restored = self.state()
        with self.assertRaisesRegex(ValueError, "RETRY_LIMIT"):
            restored.start("TASK-1")

    def test_expired_and_legacy_plans_require_replanning(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        state._clock = lambda: 1000 + state.MAX_PLAN_AGE + 1
        with self.assertRaisesRegex(ValueError, "PLAN_EXPIRED"):
            state.start("TASK-1")
        state._execution = None
        with self.assertRaisesRegex(ValueError, "zaman kaydı"):
            state.start("TASK-1")

    def test_restart_recovers_running_task_but_does_not_refresh_source_hash(self):
        repository = self.repository()
        state = self.state(repository)
        state.replace_plan(make_plan())
        state.start("TASK-1")
        (self.root / "first.py").write_text("FIRST = 99\n", encoding="utf-8")
        repository.close()
        restored = self.state()
        self.assertEqual(restored.get_task("TASK-1").status, TaskStatus.PENDING)
        with self.assertRaisesRegex(ValueError, "kaynak değişti"):
            restored.start("TASK-1")
        self.assertIn("deneme 1/3", restored.health())

    def test_approval_checks_drift_before_calling_workflow(self):
        state = self.state()
        state.replace_plan(make_plan())
        state.start("TASK-1")
        workflow = Mock(has_pending=True)
        workflow.resolve.side_effect = lambda message: setattr(workflow, "has_pending", False)
        guard = GuardedTaskWorkflow(workflow, state)
        (self.root / "second.py").write_text("SECOND = 99\n", encoding="utf-8")
        report = guard.resolve("kod değişikliğini onayla")
        self.assertIn("SOURCE_DRIFT", report)
        workflow.resolve.assert_called_once_with("iptal")

    def test_timeout_becomes_failed_task_and_explicit_retry_generates_new_proposal(self):
        state = self.state()
        state.replace_plan(make_plan())
        workflow = Mock(has_pending=False)
        workflow.resolve.side_effect = TimeoutError("model timeout")
        guard = GuardedTaskWorkflow(workflow, state)
        coordinator = TaskPlanCoordinator(
            parser=RuleBasedTaskCommandParser(), planner=Mock(), workflow=guard,
            state=state, planned_execution_enabled=True,
        )
        admin = ReliableTaskCoordinator(coordinator, state, state._repository)
        report = admin.resolve("planı çalıştır")
        self.assertIn("TIMEOUT", report)
        self.assertEqual(state.get_task("TASK-1").status, TaskStatus.FAILED)

        def propose(message):
            workflow.has_pending = True
            return "ORKESTRATÖR RAPORU\nGenel durum: ONAY BEKLİYOR"

        workflow.resolve.side_effect = propose
        self.assertIn("ONAY BEKLİYOR", admin.resolve("task yeniden dene: TASK-1"))
        self.assertIn("deneme 2/3", state.health())


class SandboxTerminalTests(TaskFixture):
    def test_canonical_command_is_sent_only_to_sandbox_executor(self):
        executor = Mock()
        executor.execute.side_effect = lambda spec: CommandExecutionResult(
            spec, 0, 0.1, "Ran 1 test in 0.001s\n\nOK\n",
        )
        terminal = SandboxTerminalCoordinator(self.root, executor)
        report = terminal.resolve("terminal: python -m unittest first.py")
        self.assertIn("BAŞARILI", report)
        self.assertEqual(executor.execute.call_args.args[0].arguments, ("-m", "unittest", "first.py"))

    def test_shell_escape_flags_and_paths_are_rejected(self):
        executor = Mock()
        terminal = SandboxTerminalCoordinator(self.root, executor)
        commands = (
            'python -c "print(1)"', 'unittest first.py; whoami', 'unittest ../outside.py',
            'ruff check --fix', 'pytest -s', 'unittest first.py | curl example.com',
            'unittest .env', 'bash', 'pip install anything',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertIn("ÇALIŞTIRILAMADI", terminal.resolve("terminal: " + command))
        executor.execute.assert_not_called()

    def test_zero_tests_and_timeouts_are_not_success(self):
        executor = Mock()
        terminal = SandboxTerminalCoordinator(self.root, executor)
        executor.execute.side_effect = lambda spec: CommandExecutionResult(spec, 0, 1, "Ran 0 tests\nOK")
        self.assertIn("TEST BULUNAMADI", terminal.resolve("terminal: unittest"))
        executor.execute.side_effect = lambda spec: CommandExecutionResult(spec, None, 120, "", timed_out=True)
        self.assertIn("ZAMAN AŞIMI", terminal.resolve("terminal: unittest"))


class ReleaseV300Tests(unittest.TestCase):
    def test_default_release_and_all_intermediate_versions(self):
        import main_v170

        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release(), "app")
            self.assertEqual(builder.call_args.kwargs["application_version"], "V3.0")
            self.assertTrue(builder.call_args.kwargs["sandbox_terminal_enabled"])
            for version in ("V2.3", "V2.4", "V2.5", "V2.6", "V2.7", "V2.8", "V2.9", "V3.0"):
                build_release(version)
                flags = builder.call_args.kwargs
                self.assertTrue(flags["reliable_tasks_enabled"])
                self.assertTrue(flags["source_drift_detection_enabled"])
                self.assertTrue(flags["planned_task_execution_enabled"])


class ApplicationRoutingTests(TaskFixture):
    def test_real_application_routes_checkpoint_and_terminal_without_model_fallback(self):
        import main_v170
        from boru.config import AppSettings

        def repository_factory(path, **kwargs):
            repository = ManagedTaskCheckpointRepository(path, **kwargs)
            self.addCleanup(repository.close)
            return repository

        with (
            patch.object(main_v170, "__file__", str(self.root / "main_v170.py")),
            patch.object(main_v170.AppSettings, "from_env", return_value=AppSettings(memory_semantic_enabled=False)),
            patch.object(main_v170, "ManagedTaskCheckpointRepository", side_effect=repository_factory),
            patch.object(main_v170, "ChatAppUI") as ui,
            patch.object(main_v170, "OllamaChatModel") as model,
            patch.object(main_v170.ModelWarmupService, "start"),
            patch.object(main_v170.DockerSandboxExecutor, "status", return_value="SANDBOX HAZIR"),
        ):
            build_release()
            assistant = ui.call_args.kwargs["assistant"]
            self.assertIn("CHECKPOINT DURUMU", assistant.reply("checkpoint durumu"))
            self.assertIn("PLAN SAĞLIĞI", assistant.reply("plan sağlığı"))
            self.assertIn("TERMİNAL ORTAMI", assistant.reply("terminal durumu"))
            self.assertIn("ÇALIŞTIRILAMADI", assistant.reply('terminal: python -c "print(1)"'))
            model.return_value.generate.assert_not_called()


@unittest.skipUnless(os.environ.get("BORU_RUN_DOCKER_TESTS") == "1", "Opt-in Docker integration")
class LiveDockerTerminalTests(TaskFixture):
    def test_real_container_pass_failure_and_source_integrity(self):
        from boru.sandbox.executor import DockerSandboxExecutor

        target = self.root / "sandbox_smoke.py"
        passing = "import unittest\nclass Smoke(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(2, 2)\n"
        target.write_text(passing, encoding="utf-8")
        terminal = SandboxTerminalCoordinator(self.root, DockerSandboxExecutor(self.root))
        report = terminal.resolve("terminal: python -m unittest sandbox_smoke.py")
        self.assertIn("Durum: BAŞARILI", report, report)
        self.assertIn("Çıkış kodu: 0", report)
        self.assertEqual(target.read_text(encoding="utf-8"), passing)
        failing = passing.replace("assertEqual(2, 2)", "assertEqual(1, 2)")
        target.write_text(failing, encoding="utf-8")
        report = terminal.resolve("terminal: unittest sandbox_smoke.py")
        self.assertIn("Durum: BAŞARISIZ", report, report)
        self.assertIn("AssertionError", report)
        self.assertEqual(target.read_text(encoding="utf-8"), failing)


if __name__ == "__main__":
    unittest.main()
