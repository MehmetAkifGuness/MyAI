import os
import tempfile
import unittest
from pathlib import Path

from boru.sandbox.executor import LocalIsolatedSandboxExecutor
from boru.tools.command_models import CommandKind, CommandRisk, CommandSpec


class SandboxHardeningTests(unittest.TestCase):
    def test_sanitized_environment_strips_sensitive_keys(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            # Test ortamında sahte hassas anahtarlar simüle et
            old_token = os.environ.get("GITHUB_TOKEN")
            old_key = os.environ.get("OPENAI_API_KEY")
            try:
                os.environ["GITHUB_TOKEN"] = "ghp_secret123456"
                os.environ["OPENAI_API_KEY"] = "sk-live-secret"

                clean_env = LocalIsolatedSandboxExecutor._sanitized_environment(root)

                self.assertNotIn("GITHUB_TOKEN", clean_env)
                self.assertNotIn("OPENAI_API_KEY", clean_env)
                self.assertEqual(clean_env.get("PYTHONPATH"), str(root))
                self.assertEqual(clean_env.get("PYTHONDONTWRITEBYTECODE"), "1")
                # Temel OS değişkenleri korunmalı
                if os.name == "nt":
                    self.assertIn("SYSTEMROOT", clean_env)
                else:
                    self.assertIn("PATH", clean_env)
            finally:
                if old_token is not None:
                    os.environ["GITHUB_TOKEN"] = old_token
                else:
                    os.environ.pop("GITHUB_TOKEN", None)
                if old_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_key
                else:
                    os.environ.pop("OPENAI_API_KEY", None)

    def test_local_executor_executes_isolated_test(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "module_a.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
            (root / "test_a.py").write_text(
                "import unittest\n"
                "from module_a import add\n"
                "class TestA(unittest.TestCase):\n"
                "    def test_add(self):\n"
                "        self.assertEqual(add(1, 2), 3)\n",
                encoding="utf-8",
            )

            executor = LocalIsolatedSandboxExecutor(root)
            cmd = CommandSpec(
                CommandKind.UNITTEST,
                "python",
                ("-m", "unittest", "test_a.py"),
                "unittest test_a.py",
                CommandRisk.SAFE,
            )
            res = executor.execute(cmd)

            self.assertEqual(res.exit_code, 0)
            self.assertIn("OK", res.output)


if __name__ == "__main__":
    unittest.main()

