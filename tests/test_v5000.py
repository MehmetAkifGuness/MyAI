import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import main_v170
from boru.autonomy import AutonomousDevelopmentCoordinator, RuleBasedAutonomyCommandParser
from boru.evaluation import Check, EvaluationReport, EvidenceEvaluator, Verdict
from boru.release import build_release
from boru.sandbox import DockerSandboxExecutor
from boru.tasks import TaskItem, TaskStatus
from boru.tasks.reliable_coordinator import ReliableTaskCoordinator


class FakeTasks:
    def __init__(self):
        self.has_pending = False
        self.calls = []

    def resolve(self, message):
        self.calls.append(message)
        if message.startswith("görev planla:"):
            return "GÖREV PLANI HAZIRLANDI\nTASK-1"
        if message in {"planı çalıştır", "planı devam ettir"}:
            self.has_pending = True
            return "PLANLI GÖREV YÜRÜTME\nDurum: ONAY BEKLİYOR"
        if message.startswith("task yeniden dene:"):
            self.has_pending = True
            return "TASK DURUMU\nTASK-1: running"
        if message == "iptal":
            self.has_pending = False
            return "İptal edildi; task pending."
        if message == "görev durumu":
            return "GÖREV DURUMU\nİlerleme: 1/1 tamamlandı"
        if message == "görev günlüğü":
            return "GÖREV GÜNLÜĞÜ\nKayıt: 2"
        if message == "planı arşivle":
            return "Görev planı arşivlendi: plan-1.json"
        return "devredildi: " + message


class FakeEvaluator:
    def __init__(self, response="ÖZ DEĞERLENDİRME RAPORU\nDurum: GEÇTİ"):
        self.response = response
        self.paths = None

    def validate_paths(self, paths):
        self.paths = paths
        return self.response


class RetryState:
    def __init__(self):
        self.task = TaskItem(
            "TASK-1",
            "Değişikliği doğrula",
            "a.py değişikliğini doğrula",
            ("a.py",),
            status=TaskStatus.FAILED,
            note="[CHANGES_APPLIED] [TEST_FAILED]",
        )

    def get_task(self, task_id):
        if task_id != self.task.task_id:
            raise ValueError(task_id)
        return self.task

    def validate_execution(self):
        return None

    def ensure_attempt_available(self, task_id):
        self.get_task(task_id)

    def health(self):
        return "PLAN SAĞLIĞI\nDurum: GEÇERLİ"

    def archive(self):
        return "archive.json"

    def reset(self, task_id):
        self.task = replace(self.get_task(task_id), status=TaskStatus.PENDING, note="")
        return self.task

    def start(self, task_id):
        self.task = replace(self.get_task(task_id), status=TaskStatus.RUNNING)
        return self.task

    def transition(self, task_id, status, note="", **kwargs):
        del kwargs
        self.task = replace(self.get_task(task_id), status=status, note=note)
        return self.task


class RetryCoordinator:
    has_pending = False

    def __init__(self):
        self.calls = []

    def resolve(self, message):
        self.calls.append(message)
        return "delegated"


class AlreadySatisfiedTasks(FakeTasks):
    def resolve(self, message):
        if message == "planı çalıştır":
            self.calls.append(message)
            return "PLANLI GÖREV YÜRÜTME\nDurum: TAMAMLANDI"
        return super().resolve(message)


class ReportEvaluator:
    def __init__(self, verdict):
        test = Check("Test", verdict, "test sonucu")
        passed = (
            Check("Security", Verdict.PASS, "temiz"),
            Check("Code Review", Verdict.PASS, "uygun"),
            Check("Kaynak bütünlüğü", Verdict.PASS, "değişmedi"),
        )
        self.report = EvaluationReport(("a.py",), (), (test, *passed))

    def evaluate(self, paths):
        if paths != ("a.py",):
            raise AssertionError(paths)
        return self.report

    def is_current(self, report):
        return report is self.report


class SupervisedAutonomyTests(unittest.TestCase):
    def test_v41_accepts_curated_typo_without_relaxing_approval(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks, feature_level=1)

        response = coordinator.resolve("otonom gelistr: a.py düzelt")

        self.assertIn("ONAY BEKLİYOR", response)
        self.assertEqual(tasks.calls[:2], ["görev planla: a.py düzelt", "planı çalıştır"])
        self.assertEqual(coordinator.resolve("kod degisikligini onayla"), "devredildi: kod degisikligini onayla")

    def test_v42_plans_without_starting_and_v43_starts_explicitly(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks, feature_level=3)

        planned = coordinator.resolve("otonom planla: a.py düzelt")
        started = coordinator.resolve("otonom başlat")

        self.assertIn("PLAN HAZIR", planned)
        self.assertFalse("planı çalıştır" in tasks.calls[:1])
        self.assertIn("ONAY BEKLİYOR", started)

    def test_v44_pause_and_v45_resume_use_checkpoint_workflow(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks, feature_level=5)
        coordinator.resolve("otonom geliştir: a.py düzelt")

        paused = coordinator.resolve("otonom duraklat")
        resumed = coordinator.resolve("otonom sürdür")

        self.assertIn("DURAKLATILDI", paused)
        self.assertIn("ONAY BEKLİYOR", resumed)
        self.assertIn("iptal", tasks.calls)

    def test_v46_retry_validates_task_identifier(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks, feature_level=6)

        self.assertIn("REDDEDİLDİ", coordinator.resolve("otonom yeniden dene: task-x"))
        self.assertIn("ONAY BEKLİYOR", coordinator.resolve("otonom yeniden dene: TASK-1"))
        self.assertIn("task yeniden dene: TASK-1", tasks.calls)

    def test_v47_targeted_verification_is_bounded_and_delegated(self):
        evaluator = FakeEvaluator()
        coordinator = AutonomousDevelopmentCoordinator(
            FakeTasks(), evaluator=evaluator, feature_level=7
        )

        response = coordinator.resolve("otonom doğrula: a.py ve tests/test_a.py")

        self.assertIn("Durum: GEÇTİ", response)
        self.assertEqual(evaluator.paths, ("a.py", "tests/test_a.py"))
        self.assertIn("DOĞRULANAMADI", coordinator.resolve("otonom doğrula: ../secret.py"))

    def test_v48_summary_v49_archive_and_limits(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks, feature_level=9)

        summary = coordinator.resolve("otonom özet")
        archive = coordinator.resolve("otonom arşivle")
        limits = coordinator.resolve("otonom sınırlar")

        self.assertIn("GÖREV DURUMU", summary)
        self.assertIn("GÖREV GÜNLÜĞÜ", summary)
        self.assertIn("ARŞİVLENDİ", archive)
        self.assertIn("12 task", limits)
        self.assertIn("açık onay", limits)
        self.assertIn("otonom iptal", coordinator.resolve("otonom yardım"))

    def test_v50_supervised_alias_still_stops_at_approval(self):
        tasks = FakeTasks()
        coordinator = AutonomousDevelopmentCoordinator(tasks, feature_level=10)

        response = coordinator.resolve("otonom denetimli geliştir: a.py düzelt")

        self.assertIn("ONAY BEKLİYOR", response)
        self.assertTrue(tasks.has_pending)
        self.assertEqual(tasks.calls[-1], "planı çalıştır")

    def test_already_satisfied_goal_reports_completed_without_approval(self):
        coordinator = AutonomousDevelopmentCoordinator(
            AlreadySatisfiedTasks(),
            feature_level=10,
        )

        response = coordinator.resolve("otonom geliştir: a.py değerini koru")

        self.assertIn("OTONOM GELİŞTİRME\nDurum: TAMAMLANDI", response)
        self.assertFalse(coordinator.has_pending)

    def test_feature_gates_hide_later_commands(self):
        parser = RuleBasedAutonomyCommandParser(1)
        self.assertIsNone(parser.parse("otonom planla: a.py düzelt"))
        self.assertNotIn("otonom planla", parser.usage())


class AppliedChangeRetryTests(unittest.TestCase):
    def test_passed_revalidation_completes_without_reapplying_patch(self):
        state = RetryState()
        coordinator = RetryCoordinator()
        reliable = ReliableTaskCoordinator(
            coordinator,
            state,
            Mock(),
            evaluator=ReportEvaluator(Verdict.PASS),
        )

        response = reliable.resolve("task yeniden dene: TASK-1")

        self.assertIn("Durum: TAMAMLANDI", response)
        self.assertIs(state.task.status, TaskStatus.COMPLETED)
        self.assertEqual(coordinator.calls, [])

    def test_failed_revalidation_does_not_reapply_same_patch(self):
        state = RetryState()
        coordinator = RetryCoordinator()
        reliable = ReliableTaskCoordinator(
            coordinator,
            state,
            Mock(),
            evaluator=ReportEvaluator(Verdict.FAIL),
        )

        response = reliable.resolve("task yeniden dene: TASK-1")

        self.assertIn("DOĞRULAMA BAŞARISIZ", response)
        self.assertIs(state.task.status, TaskStatus.FAILED)
        self.assertEqual(coordinator.calls, [])


class ReleaseV500Tests(unittest.TestCase):
    def test_v50_release_keeps_full_supervised_autonomy(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            self.assertEqual(build_release("V5.0"), "app")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V5.0")
            self.assertEqual(flags["autonomy_feature_level"], 10)
            self.assertTrue(flags["autonomous_development_enabled"])

    def test_v41_through_v50_are_independently_buildable(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            versions = tuple(f"V4.{minor}" for minor in range(1, 10)) + ("V5.0",)
            for level, version in enumerate(versions, 1):
                with self.subTest(version=version):
                    self.assertEqual(build_release(version), "app")
                    flags = builder.call_args.kwargs
                    self.assertEqual(flags["application_version"], version)
                    self.assertEqual(flags["autonomy_feature_level"], level)


@unittest.skipUnless(os.environ.get("BORU_RUN_DOCKER_TESTS") == "1", "Opt-in Docker integration")
class LiveSupervisedAutonomyTests(unittest.TestCase):
    def test_targeted_verification_uses_real_networkless_sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
            (root / "value_test.py").write_text(
                "import unittest\nfrom value import VALUE\n\n"
                "class ValueTests(unittest.TestCase):\n"
                "    def test_value(self):\n        self.assertEqual(VALUE, 2)\n",
                encoding="utf-8",
            )
            coordinator = AutonomousDevelopmentCoordinator(
                FakeTasks(),
                evaluator=EvidenceEvaluator(root, DockerSandboxExecutor(root)),
                feature_level=10,
            )

            response = coordinator.resolve("otonom doğrula: value.py")

            self.assertIn("Durum: GEÇTİ", response)
            self.assertIn("value_test.py: GEÇTİ", response)


if __name__ == "__main__":
    unittest.main()
