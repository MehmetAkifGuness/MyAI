import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory
from boru.tools import (
    ChainedToolPlanner,
    FallbackToolPlanner,
    LLMToolPlanner,
    ListDirectoryTool,
    NaturalLanguageToolPlanner,
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    RuleBasedToolCandidateDetector,
    RuleBasedToolPlanner,
    ToolCoordinator,
    ToolDecision,
    ToolExecutor,
    ToolRegistry,
    ToolResponseMode,
    ToolRisk,
)


class RecordingChatModel:
    def __init__(
        self,
        response: str,
    ):
        self.response = response
        self.calls: list[list[ChatMessage]] = []

    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        self.calls.append(list(messages))
        return self.response


class FailingChatModel:
    def __init__(self):
        self.calls = 0

    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        del messages
        self.calls += 1
        raise OSError("planner unavailable")


class StaticPlanner:
    def __init__(
        self,
        decision: ToolDecision,
    ):
        self._decision = decision

    def plan(
        self,
        user_message: str,
    ) -> ToolDecision:
        del user_message
        return self._decision


class FailClosedToolPlanningTests(
    unittest.TestCase
):
    def test_natural_planner_maps_tests_under_request(
        self,
    ) -> None:
        decision = NaturalLanguageToolPlanner().plan(
            "tests altında neler var?"
        )

        self.assertTrue(
            decision.should_use_tool
        )
        self.assertEqual(
            decision.tool_call.tool_name,  # type: ignore[union-attr]
            "list_directory",
        )
        self.assertEqual(
            decision.tool_call.arguments["path"],  # type: ignore[union-attr]
            "tests",
        )
        self.assertEqual(
            decision.response_mode,
            ToolResponseMode.DIRECT,
        )

    def test_natural_planner_maps_config_look_request(
        self,
    ) -> None:
        decision = NaturalLanguageToolPlanner().plan(
            "boru/config.py tarafına bir bak, hangi modeller kullanılıyor?"
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
        self.assertEqual(
            decision.response_mode,
            ToolResponseMode.SYNTHESIZE,
        )
        self.assertEqual(
            decision.synthesis_instruction,
            "hangi modeller kullanılıyor",
        )

    def test_natural_planner_maps_env_look_request(
        self,
    ) -> None:
        decision = NaturalLanguageToolPlanner().plan(
            ".env tarafına bakıp içeriğini özetler misin?"
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
            ".env",
        )
        self.assertEqual(
            decision.response_mode,
            ToolResponseMode.SYNTHESIZE,
        )

    def test_chained_planner_keeps_existing_rule_fast_path(
        self,
    ) -> None:
        planner = ChainedToolPlanner(
            [
                RuleBasedToolPlanner(),
                NaturalLanguageToolPlanner(),
            ]
        )

        decision = planner.plan(
            "15 * 27 kaç?"
        )

        self.assertTrue(
            decision.should_use_tool
        )
        self.assertEqual(
            decision.tool_call.tool_name,  # type: ignore[union-attr]
            "calculator",
        )

    def test_chained_planner_uses_natural_second_stage(
        self,
    ) -> None:
        planner = ChainedToolPlanner(
            [
                RuleBasedToolPlanner(),
                NaturalLanguageToolPlanner(),
            ]
        )

        decision = planner.plan(
            "tests altında neler var?"
        )

        self.assertTrue(
            decision.should_use_tool
        )
        self.assertEqual(
            decision.tool_call.tool_name,  # type: ignore[union-attr]
            "list_directory",
        )

    def test_llm_planner_failure_has_explicit_failure_state(
        self,
    ) -> None:
        model = FailingChatModel()
        planner = LLMToolPlanner(
            chat_model=model,
            registry=ToolRegistry(),
        )

        decision = planner.plan(
            "config dosyasına göz at"
        )

        self.assertFalse(
            decision.should_use_tool
        )
        self.assertTrue(
            decision.planning_failed
        )
        self.assertEqual(
            model.calls,
            1,
        )

    def test_fallback_converts_candidate_no_tool_to_failure(
        self,
    ) -> None:
        fallback_model = RecordingChatModel(
            '{"should_use_tool":false,'
            '"tool_name":null,'
            '"arguments":{},'
            '"response_mode":"direct",'
            '"synthesis_instruction":"",'
            '"reason":"emin değilim"}'
        )
        planner = FallbackToolPlanner(
            primary=ChainedToolPlanner(
                [
                    RuleBasedToolPlanner(),
                    NaturalLanguageToolPlanner(),
                ]
            ),
            fallback=LLMToolPlanner(
                chat_model=fallback_model,
                registry=ToolRegistry(),
            ),
            candidate_detector=RuleBasedToolCandidateDetector(),
        )

        decision = planner.plan(
            "config dosyasına göz atıp modeli bul"
        )

        self.assertFalse(
            decision.should_use_tool
        )
        self.assertTrue(
            decision.planning_failed
        )

    def test_non_candidate_general_chat_remains_no_tool(
        self,
    ) -> None:
        fallback_model = RecordingChatModel(
            "unused"
        )
        planner = FallbackToolPlanner(
            primary=ChainedToolPlanner(
                [
                    RuleBasedToolPlanner(),
                    NaturalLanguageToolPlanner(),
                ]
            ),
            fallback=LLMToolPlanner(
                chat_model=fallback_model,
                registry=ToolRegistry(),
            ),
        )

        decision = planner.plan(
            "Python'da decorator nedir?"
        )

        self.assertFalse(
            decision.should_use_tool
        )
        self.assertFalse(
            decision.planning_failed
        )
        self.assertEqual(
            fallback_model.calls,
            [],
        )

    def test_coordinator_returns_safe_message_on_planning_failure(
        self,
    ) -> None:
        coordinator = ToolCoordinator(
            planner=StaticPlanner(
                ToolDecision.planning_failure(
                    "planner failed"
                )
            ),
            executor=ToolExecutor(
                registry=ToolRegistry(),
                policy=RiskBasedToolPolicy(),
            ),
        )

        response = coordinator.resolve(
            "config dosyasına bak"
        )

        self.assertIn(
            "tahminde bulunmayacağım",
            response or "",
        )

    def test_assistant_never_falls_back_to_normal_llm_after_planning_failure(
        self,
    ) -> None:
        normal_model = RecordingChatModel(
            "SQLALCHEMY_DATABASE_URI ve SECRET_KEY var."
        )
        coordinator = ToolCoordinator(
            planner=StaticPlanner(
                ToolDecision.planning_failure(
                    "planner failed"
                )
            ),
            executor=ToolExecutor(
                registry=ToolRegistry(),
                policy=RiskBasedToolPolicy(),
            ),
        )
        assistant = AssistantService(
            chat_model=normal_model,
            conversation_history=ConversationHistory(),
            prompt_factory=SystemPromptFactory(
                "Börü"
            ),
            direct_response_resolvers=[
                coordinator
            ],
        )

        response = assistant.reply(
            ".env tarafına bakıp içeriğini özetler misin?"
        )

        self.assertIn(
            "tahminde bulunmayacağım",
            response,
        )
        self.assertEqual(
            normal_model.calls,
            [],
        )

    def test_real_env_natural_request_reaches_workspace_security(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = ReadOnlyWorkspace(
                directory
            )
            registry = ToolRegistry(
                [
                    ReadFileTool(
                        workspace
                    )
                ]
            )
            coordinator = ToolCoordinator(
                planner=NaturalLanguageToolPlanner(),
                executor=ToolExecutor(
                    registry=registry,
                    policy=RiskBasedToolPolicy(
                        allowed_risks=(
                            ToolRisk.READ_ONLY,
                        )
                    ),
                ),
            )

            response = coordinator.resolve(
                ".env tarafına bakıp içeriğini özetler misin?"
            )

            self.assertIn(
                "Hassas olabilecek dosyaya erişim engellendi",
                response or "",
            )

    def test_real_tests_natural_request_lists_actual_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_alpha.py").write_text(
                "pass\n",
                encoding="utf-8",
            )
            (tests / "test_beta.py").write_text(
                "pass\n",
                encoding="utf-8",
            )

            registry = ToolRegistry(
                [
                    ListDirectoryTool(
                        ReadOnlyWorkspace(root)
                    )
                ]
            )
            coordinator = ToolCoordinator(
                planner=NaturalLanguageToolPlanner(),
                executor=ToolExecutor(
                    registry=registry,
                    policy=RiskBasedToolPolicy(
                        allowed_risks=(
                            ToolRisk.READ_ONLY,
                        )
                    ),
                ),
            )

            response = coordinator.resolve(
                "tests altında neler var?"
            )

            self.assertIn(
                "test_alpha.py",
                response or "",
            )
            self.assertIn(
                "test_beta.py",
                response or "",
            )


if __name__ == "__main__":
    unittest.main()