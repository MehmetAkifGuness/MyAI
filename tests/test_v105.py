import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.memory import (
    ConservativeMemoryDecisionGate,
)
from boru.models import ChatMessage
from boru.tools import (
    CalculatorTool,
    CompositeToolResultSynthesizer,
    FallbackToolPlanner,
    GroundedLLMToolResultSynthesizer,
    JsonLLMToolPlanningParser,
    LLMToolPlanner,
    ListDirectoryTool,
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    RuleBasedToolCandidateDetector,
    RuleBasedToolPlanner,
    ToolCall,
    ToolCoordinator,
    ToolExecutor,
    ToolRegistry,
    ToolResponseMode,
    ToolRisk,
)


class SequenceChatModel:
    def __init__(
        self,
        responses: Sequence[str],
    ):
        self._responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        self.calls.append(list(messages))

        if not self._responses:
            raise AssertionError(
                "Beklenmeyen ek LLM çağrısı yapıldı."
            )

        return self._responses.pop(0)


class FailingChatModel:
    def __init__(self):
        self.calls = 0

    def generate(
        self,
        messages: Sequence[ChatMessage],
    ) -> str:
        del messages
        self.calls += 1
        raise OSError("model unavailable")


class CountingExecutor:
    def __init__(
        self,
        delegate: ToolExecutor,
    ):
        self._delegate = delegate
        self.calls: list[ToolCall] = []

    def execute(
        self,
        call: ToolCall,
    ):
        self.calls.append(call)
        return self._delegate.execute(call)


class SmarterToolPlanningTests(
    unittest.TestCase
):
    def test_json_planner_parser_accepts_fenced_json(
        self,
    ) -> None:
        payload = JsonLLMToolPlanningParser().parse(
            "```json\n"
            "{\"should_use_tool\":true,"
            "\"tool_name\":\"read_file\","
            "\"arguments\":{\"path\":\"config.py\"},"
            "\"response_mode\":\"synthesize\","
            "\"synthesis_instruction\":\"modeli söyle\","
            "\"reason\":\"dosya gerekli\"}"
            "\n```"
        )

        self.assertTrue(
            payload.should_use_tool
        )
        self.assertEqual(
            payload.tool_name,
            "read_file",
        )
        self.assertEqual(
            payload.arguments,
            {"path": "config.py"},
        )

    def test_json_planner_parser_rejects_nested_arguments(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "karmaşık argüman",
        ):
            JsonLLMToolPlanningParser().parse(
                '{"should_use_tool":true,'
                '"tool_name":"read_file",'
                '"arguments":{"path":{"nested":true}},'
                '"response_mode":"direct",'
                '"synthesis_instruction":"",'
                '"reason":"x"}'
            )

    def test_llm_planner_selects_registered_tool(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(
                [
                    ReadFileTool(
                        ReadOnlyWorkspace(directory)
                    )
                ]
            )
            model = SequenceChatModel(
                [
                    '{"should_use_tool":true,'
                    '"tool_name":"read_file",'
                    '"arguments":{"path":"config.py"},'
                    '"response_mode":"synthesize",'
                    '"synthesis_instruction":"hangi modeli kullandığımızı söyle",'
                    '"reason":"config dosyası okunmalı"}'
                ]
            )

            decision = LLMToolPlanner(
                chat_model=model,
                registry=registry,
            ).plan(
                "config dosyasına bir bak, hangi modeli kullanıyoruz?"
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
                "config.py",
            )
            self.assertEqual(
                decision.response_mode,
                ToolResponseMode.SYNTHESIZE,
            )

    def test_llm_planner_rejects_unknown_tool_fail_closed(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                '{"should_use_tool":true,'
                '"tool_name":"write_file",'
                '"arguments":{"path":"x.py"},'
                '"response_mode":"direct",'
                '"synthesis_instruction":"",'
                '"reason":"yaz"}'
            ]
        )

        decision = LLMToolPlanner(
            chat_model=model,
            registry=ToolRegistry(
                [CalculatorTool()]
            ),
        ).plan(
            "x.py dosyasını değiştir"
        )

        self.assertFalse(
            decision.should_use_tool
        )
        self.assertIn(
            "fail-closed",
            decision.reason,
        )

    def test_llm_planner_model_failure_is_fail_closed(
        self,
    ) -> None:
        model = FailingChatModel()

        decision = LLMToolPlanner(
            chat_model=model,
            registry=ToolRegistry(
                [CalculatorTool()]
            ),
        ).plan(
            "config dosyasına bak"
        )

        self.assertFalse(
            decision.should_use_tool
        )
        self.assertEqual(
            model.calls,
            1,
        )
        self.assertIn(
            "fail-closed",
            decision.reason,
        )

    def test_llm_planner_rejects_malformed_json_fail_closed(
        self,
    ) -> None:
        model = SequenceChatModel(
            ["read_file(config.py)"]
        )

        decision = LLMToolPlanner(
            chat_model=model,
            registry=ToolRegistry(
                [CalculatorTool()]
            ),
        ).plan(
            "config dosyasına bak"
        )

        self.assertFalse(
            decision.should_use_tool
        )

    def test_llm_planner_rejects_invalid_response_mode(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                '{"should_use_tool":true,'
                '"tool_name":"calculator",'
                '"arguments":{"expression":"2+2"},'
                '"response_mode":"agent_loop",'
                '"synthesis_instruction":"",'
                '"reason":"hesap"}'
            ]
        )

        decision = LLMToolPlanner(
            chat_model=model,
            registry=ToolRegistry(
                [CalculatorTool()]
            ),
        ).plan(
            "iki artı iki hesapla"
        )

        self.assertFalse(
            decision.should_use_tool
        )

    def test_llm_planner_rejects_inconsistent_no_tool_payload(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                '{"should_use_tool":false,'
                '"tool_name":"calculator",'
                '"arguments":{},'
                '"response_mode":"direct",'
                '"synthesis_instruction":"",'
                '"reason":"gerek yok"}'
            ]
        )

        decision = LLMToolPlanner(
            chat_model=model,
            registry=ToolRegistry(
                [CalculatorTool()]
            ),
        ).plan(
            "Python nedir?"
        )

        self.assertFalse(
            decision.should_use_tool
        )
        self.assertIn(
            "fail-closed",
            decision.reason,
        )

    def test_llm_planner_catalog_contains_only_registered_tools_and_hints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = SequenceChatModel(
                [
                    '{"should_use_tool":false,'
                    '"tool_name":null,'
                    '"arguments":{},'
                    '"response_mode":"direct",'
                    '"synthesis_instruction":"",'
                    '"reason":"gerek yok"}'
                ]
            )
            registry = ToolRegistry(
                [
                    ReadFileTool(
                        ReadOnlyWorkspace(directory)
                    ),
                    ListDirectoryTool(
                        ReadOnlyWorkspace(directory)
                    ),
                ]
            )

            LLMToolPlanner(
                chat_model=model,
                registry=registry,
            ).plan(
                "proje tarafına bak"
            )

            prompt = model.calls[0][1].content
            self.assertIn(
                "read_file",
                prompt,
            )
            self.assertIn(
                "list_directory",
                prompt,
            )
            self.assertIn(
                "Argüman: path",
                prompt,
            )
            self.assertNotIn(
                "write_file |",
                prompt,
            )

    def test_candidate_detector_accepts_natural_config_request(
        self,
    ) -> None:
        detector = RuleBasedToolCandidateDetector()

        self.assertTrue(
            detector.is_candidate(
                "config dosyasına bir bak, hangi modeli kullanıyoruz?"
            )
        )

    def test_candidate_detector_accepts_tests_under_request(
        self,
    ) -> None:
        detector = RuleBasedToolCandidateDetector()

        self.assertTrue(
            detector.is_candidate(
                "tests altında neler var?"
            )
        )

    def test_candidate_detector_skips_general_knowledge_question(
        self,
    ) -> None:
        detector = RuleBasedToolCandidateDetector()

        self.assertFalse(
            detector.is_candidate(
                "Python'da decorator nedir?"
            )
        )

    def test_fallback_planner_keeps_rule_based_fast_path(
        self,
    ) -> None:
        fallback_model = SequenceChatModel(
            []
        )
        planner = FallbackToolPlanner(
            primary=RuleBasedToolPlanner(),
            fallback=LLMToolPlanner(
                chat_model=fallback_model,
                registry=ToolRegistry(
                    [CalculatorTool()]
                ),
            ),
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
        self.assertEqual(
            fallback_model.calls,
            [],
        )

    def test_fallback_planner_uses_llm_for_natural_tool_request(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = SequenceChatModel(
                [
                    '{"should_use_tool":true,'
                    '"tool_name":"list_directory",'
                    '"arguments":{"path":"tests"},'
                    '"response_mode":"direct",'
                    '"synthesis_instruction":"",'
                    '"reason":"tests klasörü soruluyor"}'
                ]
            )
            registry = ToolRegistry(
                [
                    ListDirectoryTool(
                        ReadOnlyWorkspace(directory)
                    )
                ]
            )
            planner = FallbackToolPlanner(
                primary=RuleBasedToolPlanner(),
                fallback=LLMToolPlanner(
                    chat_model=model,
                    registry=registry,
                ),
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
            self.assertEqual(
                len(model.calls),
                1,
            )

    def test_fallback_planner_skips_llm_for_general_chat(
        self,
    ) -> None:
        model = SequenceChatModel(
            []
        )
        planner = FallbackToolPlanner(
            primary=RuleBasedToolPlanner(),
            fallback=LLMToolPlanner(
                chat_model=model,
                registry=ToolRegistry(
                    [CalculatorTool()]
                ),
            ),
        )

        decision = planner.plan(
            "Python'da decorator nedir?"
        )

        self.assertFalse(
            decision.should_use_tool
        )
        self.assertEqual(
            model.calls,
            [],
        )

    def test_natural_read_and_synthesis_runs_exactly_one_tool(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.py").write_text(
                'model_name: str = "llama3.1"\n'
                'memory_embedding_model: str = "qwen3-embedding:0.6b"\n',
                encoding="utf-8",
            )

            model = SequenceChatModel(
                [
                    '{"should_use_tool":true,'
                    '"tool_name":"read_file",'
                    '"arguments":{"path":"config.py"},'
                    '"response_mode":"synthesize",'
                    '"synthesis_instruction":"hangi modellerin kullanıldığını söyle",'
                    '"reason":"config okunmalı"}',
                    (
                        '{"answer":"llama3.1 ve qwen3-embedding:0.6b",'
                        '"evidence":['
                        '"model_name: str = \\\"llama3.1\\\"",'
                        '"memory_embedding_model: str = '
                        '\\\"qwen3-embedding:0.6b\\\""]}'
                    ),
                ]
            )

            registry = ToolRegistry(
                [
                    ReadFileTool(
                        ReadOnlyWorkspace(root)
                    )
                ]
            )
            executor = CountingExecutor(
                ToolExecutor(
                    registry=registry,
                    policy=RiskBasedToolPolicy(
                        allowed_risks=(
                            ToolRisk.READ_ONLY,
                        )
                    ),
                )
            )
            planner = FallbackToolPlanner(
                primary=RuleBasedToolPlanner(),
                fallback=LLMToolPlanner(
                    chat_model=model,
                    registry=registry,
                ),
            )
            coordinator = ToolCoordinator(
                planner=planner,
                executor=executor,
                synthesizer=(
                    CompositeToolResultSynthesizer(
                        fallback=(
                            GroundedLLMToolResultSynthesizer(
                                model
                            )
                        )
                    )
                ),
            )

            answer = coordinator.resolve(
                "config.py tarafına bir bak, hangi modeller kullanılıyor?"
            )

            self.assertEqual(
                answer,
                "llama3.1 ve qwen3-embedding:0.6b",
            )
            self.assertEqual(
                len(executor.calls),
                1,
            )
            self.assertEqual(
                len(model.calls),
                2,
            )

    def test_memory_gate_rejects_natural_file_tool_task(
        self,
    ) -> None:
        gate = ConservativeMemoryDecisionGate()

        self.assertFalse(
            gate.should_evaluate(
                "config dosyasına bir bak hangi modeli kullanıyoruz"
            )
        )

    def test_memory_gate_rejects_natural_tests_listing_task(
        self,
    ) -> None:
        gate = ConservativeMemoryDecisionGate()

        self.assertFalse(
            gate.should_evaluate(
                "tests altında neler var göster"
            )
        )


if __name__ == "__main__":
    unittest.main()