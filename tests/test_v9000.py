import stat
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

import main_v170
from boru.memory import ConservativeMemoryDecisionGate
from boru.release import build_release
from boru.repository import (
    GitHubRepositoryImporter,
    GitHubRepositoryPolicy,
    RepositoryCoordinator,
    RepositoryInspector,
)
from boru.tools import (
    CommandKind, CommandRequest, CommandRisk, GitCommandPolicy,
    RuleBasedGitRequestParser, ShellEnvironmentAssignmentGuard,
)


def archive(files):
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        for path, content in files.items():
            zipped.writestr("owner-repo-sha/" + path, content)
    return stream.getvalue()


class RepositoryInspectionTests(unittest.TestCase):
    def test_discovers_stack_entrypoints_tests_ci_and_license(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")
            (root / "main.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests/test_main.py").write_text("def test_ok(): pass\n", encoding="utf-8")
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/ci.yml").write_text("name: ci\n", encoding="utf-8")
            (root / "LICENSE").write_text("test license\n", encoding="utf-8")

            profile = RepositoryInspector().inspect(root)

            self.assertIn(("Python", 2), profile.languages)
            self.assertIn("FastAPI", profile.frameworks)
            self.assertIn("pytest", profile.frameworks)
            self.assertIn("main.py", profile.entry_points)
            self.assertEqual(profile.test_commands, ("python -m pytest",))
            self.assertEqual(profile.ci_files, (".github/workflows/ci.yml",))
            self.assertEqual(profile.license_files, ("LICENSE",))

    def test_task_context_ranks_matching_source_and_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payment.py").write_text("class PaymentService: pass\n", encoding="utf-8")
            (root / "test_payment.py").write_text("import payment\n", encoding="utf-8")
            (root / "noise.py").write_text("VALUE = 1\n", encoding="utf-8")

            context = RepositoryInspector().task_context(root, "PaymentService hatasını düzelt")

            self.assertEqual(context.paths[0], "payment.py")
            self.assertIn("test_payment.py", context.paths)


class GitHubImportTests(unittest.TestCase):
    def test_policy_accepts_only_simple_https_github_repository(self):
        self.assertEqual(
            GitHubRepositoryPolicy.parse("https://github.com/openai/example.git"),
            ("openai", "example"),
        )
        for url in (
            "http://github.com/openai/example", "https://evil.example/openai/example",
            "https://github.com/openai/example/issues/1", "https://user@github.com/openai/example",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                GitHubRepositoryPolicy.parse(url)

    def test_imports_bounded_archive_without_git_metadata(self):
        payload = archive({"main.py": "VALUE = 1\n", "README.md": "# Demo\n"})
        with tempfile.TemporaryDirectory() as directory:
            importer = GitHubRepositoryImporter(Path(directory), downloader=lambda url: payload)

            destination = importer.import_repository("https://github.com/acme/demo")

            self.assertEqual((destination / "main.py").read_text(encoding="utf-8"), "VALUE = 1\n")
            self.assertFalse((destination / ".git").exists())
            with self.assertRaisesRegex(ValueError, "zaten mevcut"):
                importer.import_repository("https://github.com/acme/demo")

    def test_rejects_archive_symlink(self):
        stream = BytesIO()
        with ZipFile(stream, "w") as zipped:
            item = ZipInfo("owner-repo-sha/link")
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            zipped.writestr(item, "../../outside")
        with tempfile.TemporaryDirectory() as directory:
            importer = GitHubRepositoryImporter(
                Path(directory), downloader=lambda url: stream.getvalue()
            )
            with self.assertRaisesRegex(ValueError, "sembolik"):
                importer.import_repository("https://github.com/acme/demo")

    def test_rejects_windows_style_git_metadata_path(self):
        stream = BytesIO()
        with ZipFile(stream, "w") as zipped:
            zipped.writestr("owner-repo-sha/.git\\config", "unsafe")
        with tempfile.TemporaryDirectory() as directory:
            importer = GitHubRepositoryImporter(
                Path(directory), downloader=lambda url: stream.getvalue()
            )
            with self.assertRaisesRegex(ValueError, "güvenli olmayan"):
                importer.import_repository("https://github.com/acme/demo")


class RepositoryCoordinatorTests(unittest.TestCase):
    def test_import_requires_exact_approval_then_returns_profile(self):
        payload = archive({"pyproject.toml": "[project]\nname='demo'\n", "main.py": "VALUE = 1\n"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = RepositoryCoordinator(
                root, RepositoryInspector(),
                GitHubRepositoryImporter(root, downloader=lambda url: payload),
            )

            preview = coordinator.resolve("repo içe aktar: https://github.com/acme/demo")
            self.assertIn("ONAY BEKLİYOR", preview)
            self.assertFalse((root / "repositories/github/acme/demo").exists())
            self.assertIn("onay bekliyor", coordinator.resolve("onayla"))
            result = coordinator.resolve("repo içe aktarmayı onayla")

            self.assertIn("TAMAMLANDI", result)
            self.assertIn("Python=1", result)

    def test_rejects_workspace_escape_and_memory_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = RepositoryCoordinator(
                root, RepositoryInspector(), GitHubRepositoryImporter(root, downloader=lambda url: b"")
            )
            self.assertIn("BAŞARISIZ", coordinator.resolve("repo analiz et: ../outside"))
        self.assertFalse(ConservativeMemoryDecisionGate().should_evaluate("repo analiz et"))

    def test_normalizes_common_github_repository_path_forms(self):
        payload = archive({"main.py": "VALUE = 1\n"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator = RepositoryCoordinator(
                root, RepositoryInspector(),
                GitHubRepositoryImporter(root, downloader=lambda url: payload),
            )
            coordinator.resolve("repo içe aktar: https://github.com/acme/demo")
            coordinator.resolve("repo içe aktarmayı onayla")

            for value in (
                "repositories/github/acme/demo",
                "repositories//github.com/acme/demo",
                "https://github.com/acme/demo",
            ):
                with self.subTest(value=value):
                    self.assertIn("Durum: HAZIR", coordinator.resolve(f"repo analiz et: {value}"))


class RepositoryGitAndReleaseTests(unittest.TestCase):
    def test_shell_environment_assignment_never_falls_through_to_model(self):
        guard = ShellEnvironmentAssignmentGuard()
        response = guard.resolve('$env:BORU_MODEL="qwen2.5-coder:7b"')
        self.assertIn("AYARLANMADI", response)
        self.assertIsNone(guard.resolve("BORU modeli hangisi?"))

    def test_branch_creation_is_bounded_and_requires_approval_risk(self):
        parser = RuleBasedGitRequestParser()
        request = parser.parse("git dal oluştur: boru/issue-42")
        self.assertEqual(request, CommandRequest(CommandKind.GIT_SWITCH_CREATE, "boru/issue-42"))
        command = GitCommandPolicy().build(request)
        self.assertEqual(command.arguments, ("switch", "-c", "boru/issue-42"))
        self.assertIs(command.risk, CommandRisk.REQUIRES_APPROVAL)
        for name in ("../main", "-unsafe", "feature//x", "feature/.hidden"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parser.parse(f"git dal oluştur: {name}")

    def test_v90_enables_repository_intelligence(self):
        with patch.object(main_v170, "build_application", return_value="app") as builder:
            build_release()
            self.assertEqual(builder.call_args.kwargs["application_version"], "V11.0")
            self.assertTrue(builder.call_args.kwargs["repository_intelligence_enabled"])
            build_release("V8.0")
            self.assertFalse(builder.call_args.kwargs["repository_intelligence_enabled"])


if __name__ == "__main__":
    unittest.main()
