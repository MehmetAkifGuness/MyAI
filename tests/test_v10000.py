import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

import main_v170
from boru.release import build_release
from boru.modeling import StructuredModelCascade
from boru.repository import (
    GitHubRepositoryImporter,
    RepositoryAuditLog,
    RepositoryCoordinator,
    RepositoryInspector,
    RepositoryWorkspaceRuntime,
    RepositoryWorkspaceState,
)
from boru.tools import LLMProjectEditProposalPreparer, SafeEditWorkspace
from boru.tools.edit_models import EditSource
from boru.tools.project_edit_models import ProjectEditRequest
from boru.tools.deterministic_project_edit import (
    RequestedStateAlreadySatisfied,
    FallbackProjectEditProposalPreparer,
    RuleBasedStringAliasProjectEditPreparer,
)


class FakeCoding:
    def __init__(self):
        self.has_pending = False
        self.messages = []

    def resolve(self, message):
        self.messages.append(message)
        if message.startswith("kodla:"):
            self.has_pending = True
            return "CODING AGENT ÖNERİSİ\nDurum: ONAY BEKLİYOR"
        if message == "kod değişikliğini onayla":
            self.has_pending = False
            return "Coding Agent değişikliği uygulandı.\nDurum: TAMAMLANDI"
        return "Onay bekleniyor."


class FakeEvaluator:
    def __init__(self):
        self.paths = None

    def validate_paths(self, paths):
        self.paths = paths
        return "ÖZ DEĞERLENDİRME RAPORU\nDurum: GEÇTİ"


class FakeGit:
    def __init__(self):
        self.has_pending = False
        self.messages = []

    def resolve(self, message):
        self.messages.append(message)
        return "Git komutu: git status --short --branch\nDurum: BAŞARILI"


class RepositoryWorkspaceTests(unittest.TestCase):
    def make_coordinator(self, root, runtimes):
        def factory(repo_root):
            runtime = RepositoryWorkspaceRuntime(
                repo_root, FakeCoding(), FakeEvaluator(), None
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

    def test_selected_repo_is_persisted_and_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repositories/demo").mkdir(parents=True)
            runtimes = []
            first = self.make_coordinator(root, runtimes)

            result = first.resolve("repo seç: repositories/demo")
            restored = self.make_coordinator(root, runtimes)

            self.assertIn("Durum: HAZIR", result)
            self.assertIn("repositories/demo", restored.resolve("repo durum"))
            self.assertEqual(runtimes[-1].root, (root / "repositories/demo").resolve())

    def test_missing_imported_repo_returns_exact_recovery_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = self.make_coordinator(root, [])

            result = coordinator.resolve(
                "repo seç: repositories/github/MehmetAkifGuness/MyAI"
            )

            self.assertIn("Durum: BAŞARISIZ", result)
            self.assertIn(
                "repo içe aktar: https://github.com/MehmetAkifGuness/MyAI",
                result,
            )

    def test_development_and_approval_are_bound_to_selected_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo").mkdir()
            runtimes = []
            coordinator = self.make_coordinator(root, runtimes)
            coordinator.resolve("repo seç: repo")

            preview = coordinator.resolve("repo geliştir: app.py içindeki hatayı düzelt")
            blocked = coordinator.resolve("repo seç: .")
            applied = coordinator.resolve("kod değişikliğini onayla")

            self.assertIn("ONAY BEKLİYOR", preview)
            self.assertIn("Bekleyen işlem", blocked)
            self.assertIn("TAMAMLANDI", applied)
            self.assertEqual(
                runtimes[-1].coding.messages[0],
                "kodla: app.py içindeki hatayı düzelt",
            )

    def test_verification_and_git_are_repo_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo").mkdir()
            runtimes = []
            coordinator = self.make_coordinator(root, runtimes)
            coordinator.resolve("repo seç: repo")

            result = coordinator.resolve("repo doğrula: src/app.py, tests/test_app.py")
            git = coordinator.resolve("repo git durum")

            self.assertIn("Durum: GEÇTİ", result)
            self.assertEqual(
                runtimes[-1].evaluator.paths,
                ("src/app.py", "tests/test_app.py"),
            )
            self.assertIn(".git metadata yok", git)

    def test_task_context_explains_candidate_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payment.py").write_text("class PaymentService: pass\n", encoding="utf-8")
            (root / "test_payment.py").write_text("import payment\n", encoding="utf-8")

            context = RepositoryInspector().task_context(root, "PaymentService hatası")

            self.assertEqual(dict(context.reasons)["payment.py"], "birincil kod eşleşmesi")
            self.assertEqual(dict(context.reasons)["test_payment.py"], "ilişkili test adayı")

    def test_repo_git_command_is_delegated_only_to_active_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo").mkdir()
            git = FakeGit()

            def factory(repo_root):
                return RepositoryWorkspaceRuntime(
                    repo_root, FakeCoding(), FakeEvaluator(), git
                )

            coordinator = RepositoryCoordinator(
                root,
                RepositoryInspector(),
                GitHubRepositoryImporter(root, downloader=lambda _url: b""),
                workspace_factory=factory,
                workspace_state=RepositoryWorkspaceState(root / "data/workspace.json"),
                audit_log=RepositoryAuditLog(root / "data/audit.json"),
            )
            coordinator.resolve("repo seç: repo")

            result = coordinator.resolve("repo git durum")

            self.assertIn("BAŞARILI", result)
            self.assertEqual(git.messages, ["git durum"])

    def test_v100_enables_isolated_repository_workspace(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            build_release("V10.0")
            flags = builder.call_args.kwargs
            self.assertEqual(flags["application_version"], "V10.0")
            self.assertTrue(flags["repository_workspace_enabled"])
            build_release("V9.0")
            self.assertFalse(builder.call_args.kwargs["repository_workspace_enabled"])


class ProjectEditReliabilityTests(unittest.TestCase):
    def test_already_supported_alias_is_verified_without_model_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "coordinator.py").write_text(
                'if normalized in {"benchmark durumu", "benchmark durum"}:\n'
                '    return status\n',
                encoding="utf-8",
            )
            (root / "test_coordinator.py").write_text(
                'status = coordinator.resolve("benchmark durum")\n',
                encoding="utf-8",
            )
            fallback = Mock()
            preparer = FallbackProjectEditProposalPreparer(
                RuleBasedStringAliasProjectEditPreparer(SafeEditWorkspace(root)),
                fallback,
            )

            with self.assertRaises(RequestedStateAlreadySatisfied):
                preparer.prepare_project_edit(ProjectEditRequest(
                    '"benchmark durum" yazımını "benchmark durumu" ile aynı kabul et',
                    ("coordinator.py", "test_coordinator.py"),
                    (),
                ))

            fallback.prepare_project_edit.assert_not_called()

    def test_command_alias_edit_is_grounded_without_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "coordinator.py").write_text(
                'if normalized == "benchmark durumu":\n    return status\n',
                encoding="utf-8",
            )
            (root / "test_coordinator.py").write_text(
                'status = coordinator.resolve("benchmark durumu")\n',
                encoding="utf-8",
            )
            fallback = Mock()
            edit_workspace = SafeEditWorkspace(root)
            self.assertIsNotNone(
                RuleBasedStringAliasProjectEditPreparer._source_replacement(
                    edit_workspace.read_edit_source("coordinator.py").content,
                    "benchmark durum",
                    "benchmark durumu",
                )
            )
            preparer = FallbackProjectEditProposalPreparer(
                RuleBasedStringAliasProjectEditPreparer(edit_workspace),
                fallback,
            )

            instruction = '"benchmark durum" yazımını "benchmark durumu" ile aynı kabul et'
            parsed = RuleBasedStringAliasProjectEditPreparer._REQUEST.search(instruction)
            self.assertEqual(
                (parsed.group("alias"), parsed.group("canonical")),
                ("benchmark durum", "benchmark durumu"),
            )
            proposal = preparer.prepare_project_edit(ProjectEditRequest(
                instruction,
                ("coordinator.py", "test_coordinator.py"),
                (),
            ))

            self.assertEqual(
                len(proposal.edits), 2, [edit.path for edit in proposal.edits]
            )
            self.assertIn(
                'if normalized in {"benchmark durumu", "benchmark durum"}:',
                proposal.edits[0].updated_content,
            )
            self.assertIn(
                'resolve("benchmark durum")', proposal.edits[1].updated_content
            )
            fallback.prepare_project_edit.assert_not_called()

    def test_model_timeout_uses_structured_fallback_attempt(self):
        primary = Mock()
        primary.generate_structured.side_effect = TimeoutError("timed out")
        fallback = Mock()
        fallback.generate_structured.return_value = (
            '{"patches":[{"path":"a.py","old_text":"VALUE = 1",'
            '"new_text":"VALUE = 2","reason":"fix"}],"creates":[]}'
        )
        workspace = Mock()
        workspace.read_edit_source.return_value = EditSource(
            "a.py", "VALUE = 1\n", "sha"
        )
        preparer = LLMProjectEditProposalPreparer(
            chat_model=StructuredModelCascade(primary, fallback),
            file_index=Mock(),
            file_selector=Mock(),
            workspace=workspace,
            max_attempts=2,
        )

        proposal = preparer.prepare_project_edit(
            ProjectEditRequest("VALUE değerini 2 yap", ("a.py",), ())
        )

        self.assertEqual(proposal.edits[0].updated_content, "VALUE = 2\n")
        primary.generate_structured.assert_called_once()
        fallback.generate_structured.assert_called_once()

    def test_fallback_gets_one_grounding_repair_after_primary_timeout(self):
        primary = Mock()
        primary.generate_structured.side_effect = TimeoutError("timed out")
        fallback = Mock()
        fallback.generate_structured.side_effect = [
            (
                '{"patches":[{"path":"a.py","old_text":"VALUE = 9",'
                '"new_text":"VALUE = 2","reason":"fix"}],"creates":[]}'
            ),
            (
                '{"patches":[{"path":"a.py","old_text":"VALUE = 1",'
                '"new_text":"VALUE = 2","reason":"fix"}],"creates":[]}'
            ),
        ]
        workspace = Mock()
        workspace.read_edit_source.return_value = EditSource(
            "a.py", "VALUE = 1\n", "sha"
        )
        preparer = LLMProjectEditProposalPreparer(
            chat_model=StructuredModelCascade(primary, fallback),
            file_index=Mock(),
            file_selector=Mock(),
            workspace=workspace,
            max_attempts=3,
        )

        proposal = preparer.prepare_project_edit(
            ProjectEditRequest("VALUE değerini 2 yap", ("a.py",), ())
        )

        self.assertEqual(proposal.edits[0].updated_content, "VALUE = 2\n")
        self.assertEqual(fallback.generate_structured.call_count, 2)
        repair_prompt = fallback.generate_structured.call_args.args[0][-1].content
        self.assertIn("old_text kaynakta bulunamadı", repair_prompt)

    def test_large_source_context_keeps_header_and_target_window(self):
        content = "import os\n" + "".join(
            f"LINE_{index} = {index}\n" for index in range(500)
        ) + 'STATUS = "benchmark durumu"\n'

        excerpt = LLMProjectEditProposalPreparer._excerpt(
            content, '"benchmark durum" yazımını destekle', 4096
        )

        self.assertIn("import os", excerpt)
        self.assertIn('STATUS = "benchmark durumu"', excerpt)
        self.assertLessEqual(len(excerpt), 4096)


if __name__ == "__main__":
    unittest.main()
