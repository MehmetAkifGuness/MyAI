import unittest
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.models import ChatMessage
from boru.prompts import SystemPromptFactory
from boru.tools import (
    CalculatorTool,
    CurrentTimeTool,
    RiskBasedToolPolicy,
    RuleBasedToolPlanner,
    ToolCall,
    ToolCoordinator,
    ToolExecutor,
    ToolRegistry,
    ToolResult,
    ToolRisk,
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


class ReadOnlyDummyTool:
    @property
    def name(self) -> str:
        return "read_dummy"

    @property
    def description(self) -> str:
        return "Read-only test tool."

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.READ_ONLY

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            success=True,
            content="ok",
        )


class ToolCoreTests(unittest.TestCase):
    def test_tool_call_arguments_are_immutable(self) -> None:
        call = ToolCall(
            tool_name="calculator",
            arguments={"expression": "2 + 2"},
        )

        with self.assertRaises(TypeError):
            call.arguments["expression"] = "9 + 9"  # type: ignore[index]

    def test_registry_rejects_duplicate_tool_names(self) -> None:
        registry = ToolRegistry(
            [CalculatorTool()]
        )

        with self.assertRaisesRegex(
            ValueError,
            "zaten kayıtlı",
        ):
            registry.register(
                CalculatorTool()
            )

    def test_registry_exposes_tool_definition(self) -> None:
        registry = ToolRegistry(
            [CalculatorTool()]
        )

        definitions = registry.definitions()

        self.assertEqual(
            len(definitions),
            1,
        )
        self.assertEqual(
            definitions[0].name,
            "calculator",
        )
        self.assertEqual(
            definitions[0].risk,
            ToolRisk.SAFE,
        )

    def test_policy_blocks_non_allowed_risk(self) -> None:
        registry = ToolRegistry(
            [ReadOnlyDummyTool()]
        )
        executor = ToolExecutor(
            registry=registry,
            policy=RiskBasedToolPolicy(
                allowed_risks=(
                    ToolRisk.SAFE,
                )
            ),
        )

        result = executor.execute(
            ToolCall(
                tool_name="read_dummy"
            )
        )

        self.assertFalse(result.success)
        self.assertIn(
            "engellendi",
            result.error or "",
        )

    def test_executor_rejects_unknown_tool(self) -> None:
        executor = ToolExecutor(
            registry=ToolRegistry(),
            policy=RiskBasedToolPolicy(),
        )

        result = executor.execute(
            ToolCall(
                tool_name="unknown_tool"
            )
        )

        self.assertFalse(result.success)
        self.assertIn(
            "kayıtlı değil",
            result.error or "",
        )

    def test_calculator_respects_operator_precedence(self) -> None:
        result = CalculatorTool().execute(
            {
                "expression": "15 + 3 * 4",
            }
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.content,
            "27",
        )

    def test_calculator_rejects_code_execution_expression(self) -> None:
        executor = ToolExecutor(
            registry=ToolRegistry(
                [CalculatorTool()]
            ),
            policy=RiskBasedToolPolicy(),
        )

        result = executor.execute(
            ToolCall(
                tool_name="calculator",
                arguments={
                    "expression": "__import__('os').system('echo x')",
                },
            )
        )

        self.assertFalse(result.success)

    def test_calculator_rejects_extreme_exponent(self) -> None:
        executor = ToolExecutor(
            registry=ToolRegistry(
                [CalculatorTool()]
            ),
            policy=RiskBasedToolPolicy(),
        )

        result = executor.execute(
            ToolCall(
                tool_name="calculator",
                arguments={
                    "expression": "2 ** 1000",
                },
            )
        )

        self.assertFalse(result.success)
        self.assertIn(
            "Üs değeri",
            result.error or "",
        )

    def test_current_time_uses_injected_clock(self) -> None:
        fixed = datetime(
            2026,
            9,
            4,
            8,
            48,
            30,
            tzinfo=timezone(
                timedelta(hours=3)
            ),
        )

        result = CurrentTimeTool(
            clock=lambda: fixed
        ).execute({})

        self.assertEqual(
            result.content,
            "Yerel tarih ve saat: 04.09.2026 08:48:30 (+03:00)",
        )

    def test_planner_detects_symbolic_calculation(self) -> None:
        decision = RuleBasedToolPlanner().plan(
            "15 * 27 kaç?"
        )

        self.assertTrue(
            decision.should_use_tool
        )
        self.assertIsNotNone(
            decision.tool_call
        )
        self.assertEqual(
            decision.tool_call.tool_name,  # type: ignore[union-attr]
            "calculator",
        )
        self.assertEqual(
            decision.tool_call.arguments["expression"],  # type: ignore[union-attr]
            "15 * 27",
        )

    def test_planner_detects_turkish_word_operators(self) -> None:
        decision = RuleBasedToolPlanner().plan(
            "25 artı 17 kaç?"
        )

        self.assertEqual(
            decision.tool_call.arguments["expression"],  # type: ignore[union-attr]
            "25 + 17",
        )

    def test_planner_detects_current_time_request(self) -> None:
        decision = RuleBasedToolPlanner().plan(
            "Şu an saat kaç?"
        )

        self.assertTrue(
            decision.should_use_tool
        )
        self.assertEqual(
            decision.tool_call.tool_name,  # type: ignore[union-attr]
            "get_current_time",
        )

    def test_planner_leaves_general_question_to_llm(self) -> None:
        decision = RuleBasedToolPlanner().plan(
            "Python'da decorator nedir?"
        )

        self.assertFalse(
            decision.should_use_tool
        )

    def test_coordinator_returns_calculator_result(self) -> None:
        coordinator = ToolCoordinator(
            planner=RuleBasedToolPlanner(),
            executor=ToolExecutor(
                registry=ToolRegistry(
                    [CalculatorTool()]
                ),
                policy=RiskBasedToolPolicy(),
            ),
        )

        self.assertEqual(
            coordinator.resolve(
                "15 * 27 kaç?"
            ),
            "405",
        )

    def test_assistant_tool_response_bypasses_chat_model(self) -> None:
        model = RecordingChatModel()
        history = ConversationHistory()
        coordinator = ToolCoordinator(
            planner=RuleBasedToolPlanner(),
            executor=ToolExecutor(
                registry=ToolRegistry(
                    [CalculatorTool()]
                ),
                policy=RiskBasedToolPolicy(),
            ),
        )
        assistant = AssistantService(
            chat_model=model,
            conversation_history=history,
            prompt_factory=SystemPromptFactory(
                "Börü"
            ),
            direct_response_resolvers=[
                coordinator
            ],
        )

        result = assistant.reply(
            "15 * 27 kaç?"
        )

        self.assertEqual(
            result,
            "405",
        )
        self.assertEqual(
            model.calls,
            [],
        )

        snapshot = history.snapshot()
        self.assertEqual(
            snapshot[-1].content,
            "405",
        )


if __name__ == "__main__":
    unittest.main()