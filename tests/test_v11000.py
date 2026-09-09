import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main_v170
from boru.architecture import RuleBasedArchitectureRequestParser
from boru.improvement.natural import NaturalLanguageImprovementCoordinator
from boru.release import build_release
from boru.repository import (
    GitHubRepositoryImporter,
    IntelligentRepositoryTaskAnalyzer,
    RepositoryAuditLog,
    RepositoryCoordinator,
    RepositoryInspector,
    RepositoryWorkspaceRuntime,
    RepositoryWorkspaceState,
)


class FakeCoding:
    def __init__(self):
        self.has_pending = False
        self.messages = []

    def resolve(self, message):
        self.messages.append(message)
        self.has_pending = message.startswith("kodla:")
        return "CODING AGENT ÖNERİSİ\nDurum: ONAY BEKLİYOR"


class FakeEvaluator:
    def validate_paths(self, paths):
        return "Durum: GEÇTİ"


def make_coordinator(root: Path, runtimes: list) -> RepositoryCoordinator:
    def factory(repo_root):
        runtime = RepositoryWorkspaceRuntime(
            repo_root,
            FakeCoding(),
            FakeEvaluator(),
            None,
            task_analyzer=IntelligentRepositoryTaskAnalyzer(),
        )
        runtimes.append(runtime)
        return runtime

    return RepositoryCoordinator(
        root,
        RepositoryInspector(),
        GitHubRepositoryImporter(root, downloader=lambda _url: b""),
        workspace_factory=factory,
        workspace_state=RepositoryWorkspaceState(root / "data/workspace.json"),
        audit_log=RepositoryAuditLog(root / "data/audit.json"),
    )


class IntelligentTaskAnalyzerTests(unittest.TestCase):
    def test_repo_smart_development_is_not_captured_by_global_change_flow(self):
        message = "repo akıllı geliştir: benchmark sorununu düzelt"

        self.assertFalse(
            NaturalLanguageImprovementCoordinator._is_natural_change_request(
                message, message.casefold()
            )
        )

    def test_explicit_task_has_explainable_code_and_test_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pricing.py").write_text("def total(): return 1\n", encoding="utf-8")
            (root / "test_pricing.py").write_text("import pricing\n", encoding="utf-8")

            brief = IntelligentRepositoryTaskAnalyzer().analyze(
                root,
                "pricing.py içindeki total hatasını düzelt; sonuç 2 olmalı",
            )

            self.assertEqual(brief.kind, "hata düzeltme")
            self.assertEqual(brief.confidence, "yüksek")
            self.assertIsNone(brief.clarification)
            self.assertIn("pricing.py", brief.paths)
            self.assertIn("test_pricing.py", brief.test_paths)
            self.assertEqual(
                dict(brief.reasons)["pricing.py"],
                "kullanıcının açıkça belirttiği dosya",
            )

    def test_vague_goal_asks_one_question_before_coding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            (repo / "login.py").write_text("def login(): pass\n", encoding="utf-8")
            (repo / "test_login.py").write_text("import login\n", encoding="utf-8")
            runtimes = []
            coordinator = make_coordinator(root, runtimes)
            coordinator.resolve("repo seç: repo")

            question = coordinator.resolve("repo akıllı geliştir: giriş sorununu düzelt")

            self.assertIn("NETLEŞTİRME GEREKLİ", question)
            self.assertIn("Soru:", question)
            self.assertEqual(runtimes[-1].coding.messages, [])
            self.assertTrue(coordinator.has_pending)

            preview = coordinator.resolve(
                "login.py içindeki login fonksiyonu False yerine True dönmeli"
            )

            self.assertIn("ONAY BEKLİYOR", preview)
            self.assertEqual(len(runtimes[-1].coding.messages), 1)
            request = runtimes[-1].coding.messages[0]
            self.assertIn("Kullanıcı açıklaması", request)
            self.assertIn("DOĞRULAMA_KANITI:", request)
            self.assertIn("BORU_DOSYA_KAPSAMI: login.py", request)
            self.assertIn("login.py", request)

    def test_analysis_does_not_start_coding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            (repo / "service.py").write_text("class Service: pass\n", encoding="utf-8")
            runtimes = []
            coordinator = make_coordinator(root, runtimes)
            coordinator.resolve("repo seç: repo")

            result = coordinator.resolve(
                "repo akıllı analiz: service.py içindeki Service sınıfını açıkla"
            )

            self.assertIn("Durum: HAZIR", result)
            self.assertIn("araştırma/açıklama", result)
            self.assertEqual(runtimes[-1].coding.messages, [])

    def test_evidence_candidates_do_not_expand_edit_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "boru/benchmark").mkdir(parents=True)
            (repo / "tests").mkdir()
            (repo / "boru/benchmark/coordinator.py").write_text(
                "def resolve(): pass\n", encoding="utf-8"
            )
            (repo / "boru/benchmark/runner.py").write_text(
                "def run(): pass\n", encoding="utf-8"
            )
            (repo / "tests/test_v7000.py").write_text(
                "from boru.benchmark import coordinator\n", encoding="utf-8"
            )
            runtimes = []
            coordinator = make_coordinator(root, runtimes)
            coordinator.resolve("repo seç: repo")
            coordinator.resolve("repo akıllı geliştir: benchmark sorununu düzelt")

            coordinator.resolve(
                'boru/benchmark/coordinator.py içinde "benchmark durum" yazımı '
                '"benchmark durumu" ile aynı çalışmalı; tests/test_v7000.py ile doğrula'
            )

            task = runtimes[-1].coding.messages[0].removeprefix("kodla: ")
            request = RuleBasedArchitectureRequestParser().parse_task(task)
            self.assertEqual(
                request.file_scope,
                ("boru/benchmark/coordinator.py", "tests/test_v7000.py"),
            )

    def test_ui_placeholder_is_removed_from_clarification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "boru/benchmark").mkdir(parents=True)
            (repo / "tests").mkdir()
            (repo / "boru/benchmark/coordinator.py").write_text(
                "def resolve(): pass\n", encoding="utf-8"
            )
            (repo / "tests/test_v7000.py").write_text(
                "from boru.benchmark import coordinator\n", encoding="utf-8"
            )
            runtimes = []
            coordinator = make_coordinator(root, runtimes)
            coordinator.resolve("repo seç: repo")
            question = coordinator.resolve(
                "repo akıllı geliştir: benchmark sorununu düzelt"
            )
            self.assertNotIn("Düzenleme kapsamı:", question)

            coordinator.resolve(
                'Mesajınızı yazın...boru/benchmark/coordinator.py içinde '
                '"benchmark durum" yazımı "benchmark durumu" ile aynı çalışmalı; '
                'tests/test_v7000.py ile doğrula'
            )

            task = runtimes[-1].coding.messages[0].removeprefix("kodla: ")
            request = RuleBasedArchitectureRequestParser().parse_task(task)
            self.assertEqual(
                request.file_scope,
                ("boru/benchmark/coordinator.py", "tests/test_v7000.py"),
            )
            self.assertNotIn("Mesajınızı yazın", request.task)

    def test_repo_switch_is_blocked_during_clarification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo").mkdir()
            (root / "other").mkdir()
            (root / "repo/app.py").write_text("VALUE = 1\n", encoding="utf-8")
            coordinator = make_coordinator(root, [])
            coordinator.resolve("repo seç: repo")
            coordinator.resolve("repo akıllı geliştir: düzelt")

            result = coordinator.resolve("repo seç: other")

            self.assertIn("Bekleyen işlem", result)

    def test_v110_is_default_and_enables_intelligent_intake(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            build_release()

            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V11.0")
            self.assertTrue(flags["intelligent_task_intake_enabled"])

            build_release("V10.0")
            self.assertFalse(builder.call_args.kwargs["intelligent_task_intake_enabled"])


if __name__ == "__main__":
    unittest.main()
