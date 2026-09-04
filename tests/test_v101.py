import os
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.memory import ConservativeMemoryDecisionGate
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory
from boru.tools import (
    ListDirectoryTool,
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    RuleBasedToolPlanner,
    ToolCoordinator,
    ToolExecutor,
    ToolRegistry,
    ToolRisk,
    WorkspaceAccessError,
    WorkspacePathResolver,
)


class RecordingChatModel:
    def __init__(self):
        self.calls: list[list[ChatMessage]] = []

    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        self.calls.append(list(messages))
        return "LLM cevabı"


class ReadOnlyFilesystemToolTests(
    unittest.TestCase
):
    def test_planner_detects_read_file_request(
        self,
    ) -> None:
        decision = RuleBasedToolPlanner().plan(
            "boru/config.py dosyasını oku."
        )

        self.assertTrue(
            decision.should_use_tool
        )
        self.assertEqual(
            decision.tool_call.tool_name,  # type: ignore[union-attr]
            "read_file",
        )
        self.assertEqual(
            decision.tool_call.arguments["path"],  # type: ignore[union-attr]
            "boru/config.py",
        )

    def test_planner_detects_root_directory_request(
        self,
    ) -> None:
        decision = RuleBasedToolPlanner().plan(
            "Proje klasöründeki dosyaları göster."
        )

        self.assertEqual(
            decision.tool_call.tool_name,  # type: ignore[union-attr]
            "list_directory",
        )
        self.assertEqual(
            decision.tool_call.arguments["path"],  # type: ignore[union-attr]
            ".",
        )

    def test_planner_detects_subdirectory_request(
        self,
    ) -> None:
        decision = RuleBasedToolPlanner().plan(
            "tests klasörünü listele."
        )

        self.assertEqual(
            decision.tool_call.arguments["path"],  # type: ignore[union-attr]
            "tests",
        )

    def test_planner_supports_quoted_path_with_spaces(
        self,
    ) -> None:
        decision = RuleBasedToolPlanner().plan(
            '"docs/my notes.txt" dosyasını oku.'
        )

        self.assertEqual(
            decision.tool_call.arguments["path"],  # type: ignore[union-attr]
            "docs/my notes.txt",
        )

    def test_resolver_rejects_parent_traversal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resolver = WorkspacePathResolver(
                directory
            )

            with self.assertRaisesRegex(
                WorkspaceAccessError,
                "Workspace dışına",
            ):
                resolver.resolve(
                    "../secret.txt"
                )

    def test_resolver_rejects_windows_absolute_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resolver = WorkspacePathResolver(
                directory
            )

            with self.assertRaisesRegex(
                WorkspaceAccessError,
                "Mutlak",
            ):
                resolver.resolve(
                    r"C:\Windows\win.ini"
                )

    def test_resolver_rejects_sensitive_env_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "SECRET=value",
                encoding="utf-8",
            )

            workspace = ReadOnlyWorkspace(
                directory
            )

            with self.assertRaisesRegex(
                WorkspaceAccessError,
                "Hassas",
            ):
                workspace.read_text_file(
                    ".env"
                )

    def test_directory_listing_hides_sensitive_entries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "print('ok')",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "TOKEN=x",
                encoding="utf-8",
            )

            listing = ReadOnlyWorkspace(
                root
            ).list_directory()

            names = {
                entry.name
                for entry in listing.entries
            }

            self.assertIn(
                "app.py",
                names,
            )
            self.assertNotIn(
                ".env",
                names,
            )

    def test_workspace_reads_utf8_bom_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.txt"
            path.write_text(
                "Türkçe içerik",
                encoding="utf-8-sig",
            )

            content = ReadOnlyWorkspace(
                directory
            ).read_text_file(
                "note.txt"
            )

            self.assertEqual(
                content,
                "Türkçe içerik",
            )

    def test_workspace_rejects_binary_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.bin"
            path.write_bytes(
                b"abc\x00def"
            )

            with self.assertRaisesRegex(
                WorkspaceAccessError,
                "Binary",
            ):
                ReadOnlyWorkspace(
                    directory
                ).read_text_file(
                    "image.bin"
                )

    def test_workspace_rejects_oversized_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.txt"
            path.write_text(
                "x" * 11,
                encoding="utf-8",
            )

            workspace = ReadOnlyWorkspace(
                directory,
                max_file_bytes=10,
            )

            with self.assertRaisesRegex(
                WorkspaceAccessError,
                "boyutunu aşıyor",
            ):
                workspace.read_text_file(
                    "large.txt"
                )

    def test_workspace_rejects_symlink_access(
        self,
    ) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest(
                "Platform symlink desteklemiyor."
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real.txt"
            target.write_text(
                "secret",
                encoding="utf-8",
            )
            link = root / "link.txt"

            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest(
                    "Symlink oluşturma izni yok."
                )

            with self.assertRaisesRegex(
                WorkspaceAccessError,
                "Sembolik",
            ):
                ReadOnlyWorkspace(
                    root
                ).read_text_file(
                    "link.txt"
                )

    def test_read_file_tool_returns_file_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.py").write_text(
                'MODEL = "llama3.1"\n',
                encoding="utf-8",
            )

            result = ReadFileTool(
                ReadOnlyWorkspace(root)
            ).execute(
                {
                    "path": "config.py",
                }
            )

            self.assertTrue(
                result.success
            )
            self.assertIn(
                'MODEL = "llama3.1"',
                result.content,
            )

    def test_list_directory_tool_formats_entries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "boru").mkdir()
            (root / "main.py").write_text(
                "pass",
                encoding="utf-8",
            )

            result = ListDirectoryTool(
                ReadOnlyWorkspace(root)
            ).execute({})

            self.assertIn(
                "[DIR] boru",
                result.content,
            )
            self.assertIn(
                "[FILE] main.py",
                result.content,
            )

    def test_read_only_tools_require_read_only_policy_permission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.txt").write_text(
                "hello",
                encoding="utf-8",
            )
            tool = ReadFileTool(
                ReadOnlyWorkspace(root)
            )
            registry = ToolRegistry(
                [tool]
            )

            blocked = ToolExecutor(
                registry=registry,
                policy=RiskBasedToolPolicy(
                    allowed_risks=(
                        ToolRisk.SAFE,
                    )
                ),
            ).execute(
                RuleBasedToolPlanner().plan(
                    "note.txt dosyasını oku."
                ).tool_call  # type: ignore[arg-type]
            )

            allowed = ToolExecutor(
                registry=registry,
                policy=RiskBasedToolPolicy(
                    allowed_risks=(
                        ToolRisk.READ_ONLY,
                    )
                ),
            ).execute(
                RuleBasedToolPlanner().plan(
                    "note.txt dosyasını oku."
                ).tool_call  # type: ignore[arg-type]
            )

            self.assertFalse(
                blocked.success
            )
            self.assertTrue(
                allowed.success
            )

    def test_assistant_read_file_response_bypasses_llm(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.txt").write_text(
                "Börü file tool çalışıyor.",
                encoding="utf-8",
            )

            model = RecordingChatModel()
            coordinator = ToolCoordinator(
                planner=RuleBasedToolPlanner(),
                executor=ToolExecutor(
                    registry=ToolRegistry(
                        [
                            ReadFileTool(
                                ReadOnlyWorkspace(root)
                            )
                        ]
                    ),
                    policy=RiskBasedToolPolicy(
                        allowed_risks=(
                            ToolRisk.READ_ONLY,
                        )
                    ),
                ),
            )

            assistant = AssistantService(
                chat_model=model,
                conversation_history=(
                    ConversationHistory()
                ),
                prompt_factory=(
                    SystemPromptFactory(
                        "Börü"
                    )
                ),
                direct_response_resolvers=[
                    coordinator
                ],
            )

            response = assistant.reply(
                "note.txt dosyasını oku."
            )

            self.assertIn(
                "Börü file tool çalışıyor.",
                response,
            )
            self.assertEqual(
                model.calls,
                [],
            )

    def test_memory_gate_rejects_one_time_file_tool_commands(
        self,
    ) -> None:
        gate = ConservativeMemoryDecisionGate()

        self.assertFalse(
            gate.should_evaluate(
                "boru/config.py dosyasını oku."
            )
        )
        self.assertFalse(
            gate.should_evaluate(
                "tests klasörünü listele."
            )
        )


if __name__ == "__main__":
    unittest.main()