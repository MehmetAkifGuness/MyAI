import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.models import ChatMessage
from boru.tools import (
    AssignmentRequiredEvidenceExtractor,
    CompositeToolResultSynthesizer,
    DirectoryCountSynthesisResolver,
    GroundedLLMToolResultSynthesizer,
    GroundedSynthesisPayload,
    GroundedSynthesisValidator,
    JsonGroundedSynthesisParser,
    ListDirectoryTool,
    ReadFileTool,
    ReadOnlyWorkspace,
    RequiredEvidenceFact,
    ToolCall,
    ToolResult,
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


class RecordingFallbackSynthesizer:
    def __init__(
        self,
        response: str = "fallback",
    ):
        self.response = response
        self.calls: list[dict[str, object]] = []

    def synthesize(
        self,
        *,
        user_message: str,
        instruction: str,
        tool_call: ToolCall,
        tool_result: ToolResult,
    ) -> str:
        self.calls.append(
            {
                "user_message": user_message,
                "instruction": instruction,
                "tool_call": tool_call,
                "tool_result": tool_result,
            }
        )
        return self.response


class GroundedToolSynthesisTests(
    unittest.TestCase
):
    @staticmethod
    def _config_tool_result() -> ToolResult:
        return ToolResult(
            tool_name="read_file",
            success=True,
            content=(
                "Dosya: boru/config.py\n"
                "model_name: str = \"llama3.1\"\n"
                "assistant_name: str = \"Börü\"\n"
                "memory_embedding_model: str = "
                "\"qwen3-embedding:0.6b\"\n"
            ),
            metadata={
                "path": "boru/config.py",
            },
        )

    def test_tool_result_metadata_is_immutable(
        self,
    ) -> None:
        result = ToolResult(
            tool_name="list_directory",
            success=True,
            content="ok",
            metadata={
                "entry_count": 3,
            },
        )

        with self.assertRaises(TypeError):
            result.metadata["entry_count"] = 99  # type: ignore[index]

    def test_workspace_listing_retains_total_before_truncation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            for index in range(5):
                (root / f"file_{index}.txt").write_text(
                    "x",
                    encoding="utf-8",
                )

            listing = ReadOnlyWorkspace(
                root,
                max_directory_entries=2,
            ).list_directory()

            self.assertEqual(
                len(listing.entries),
                2,
            )
            self.assertTrue(
                listing.truncated
            )
            self.assertEqual(
                listing.total_entries,
                5,
            )

    def test_list_directory_tool_exposes_exact_count_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            for name in (
                "a.txt",
                "b.txt",
                "c.txt",
            ):
                (root / name).write_text(
                    "x",
                    encoding="utf-8",
                )

            result = ListDirectoryTool(
                ReadOnlyWorkspace(root)
            ).execute({})

            self.assertEqual(
                result.metadata["entry_count"],
                3,
            )
            self.assertEqual(
                result.metadata["display_path"],
                "proje kökü",
            )
            self.assertIn(
                "Toplam öğe: 3",
                result.content,
            )

    def test_directory_count_resolver_uses_metadata_not_visible_lines(
        self,
    ) -> None:
        resolver = DirectoryCountSynthesisResolver()
        result = ToolResult(
            tool_name="list_directory",
            success=True,
            content=(
                "Klasör: tests\n"
                "[FILE] tests/a.py"
            ),
            metadata={
                "entry_count": 21,
                "display_path": "tests",
                "truncated": True,
            },
        )

        answer = resolver.resolve(
            user_message=(
                "tests klasörünü listele ve kaç öğe olduğunu söyle."
            ),
            instruction="kaç öğe olduğunu söyle",
            tool_call=ToolCall(
                tool_name="list_directory",
                arguments={"path": "tests"},
            ),
            tool_result=result,
        )

        self.assertEqual(
            answer,
            "tests klasöründe 21 öğe var.",
        )

    def test_composite_count_answer_bypasses_llm_fallback(
        self,
    ) -> None:
        fallback = RecordingFallbackSynthesizer()
        synthesizer = CompositeToolResultSynthesizer(
            resolvers=[
                DirectoryCountSynthesisResolver(),
            ],
            fallback=fallback,
        )

        answer = synthesizer.synthesize(
            user_message=(
                "tests klasörünü listele ve kaç öğe olduğunu söyle."
            ),
            instruction="kaç öğe olduğunu söyle",
            tool_call=ToolCall(
                tool_name="list_directory",
                arguments={"path": "tests"},
            ),
            tool_result=ToolResult(
                tool_name="list_directory",
                success=True,
                content="Klasör: tests",
                metadata={
                    "entry_count": 17,
                    "display_path": "tests",
                },
            ),
        )

        self.assertEqual(
            answer,
            "tests klasöründe 17 öğe var.",
        )
        self.assertEqual(
            fallback.calls,
            [],
        )

    def test_json_grounded_parser_accepts_fenced_json(
        self,
    ) -> None:
        payload = JsonGroundedSynthesisParser().parse(
            "```json\n"
            "{\"answer\":\"Model llama3.1.\","
            "\"evidence\":[\"model_name: str = \\\"llama3.1\\\"\"]}"
            "\n```"
        )

        self.assertEqual(
            payload.answer,
            "Model llama3.1.",
        )
        self.assertEqual(
            len(payload.evidence),
            1,
        )

    def test_json_grounded_parser_rejects_empty_evidence(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "en az bir kanıt",
        ):
            JsonGroundedSynthesisParser().parse(
                '{"answer":"x","evidence":[]}'
            )

    def test_assignment_extractor_finds_all_model_assignments(
        self,
    ) -> None:
        facts = AssignmentRequiredEvidenceExtractor().extract(
            instruction=(
                "hangi modellerin kullanıldığını söyle"
            ),
            tool_result=self._config_tool_result(),
        )

        self.assertEqual(
            [fact.identifier for fact in facts],
            [
                "model_name",
                "memory_embedding_model",
            ],
        )
        self.assertEqual(
            [fact.value for fact in facts],
            [
                "llama3.1",
                "qwen3-embedding:0.6b",
            ],
        )

    def test_assignment_extractor_does_not_force_plural_for_singular_request(
        self,
    ) -> None:
        facts = AssignmentRequiredEvidenceExtractor().extract(
            instruction=(
                "hangi modeli kullandığımı söyle"
            ),
            tool_result=self._config_tool_result(),
        )

        self.assertEqual(
            facts,
            (),
        )

    def test_validator_rejects_evidence_not_in_source(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "kanıt tool sonucunda bulunmuyor",
        ):
            GroundedSynthesisValidator().validate(
                payload=GroundedSynthesisPayload(
                    answer="Model llama3.1.",
                    evidence=(
                        'model_name = "gpt-5"',
                    ),
                ),
                tool_result=self._config_tool_result(),
            )

    def test_validator_requires_every_required_fact_in_answer(
        self,
    ) -> None:
        result = self._config_tool_result()
        required = (
            RequiredEvidenceFact(
                source_line=(
                    'model_name: str = "llama3.1"'
                ),
                identifier="model_name",
                value="llama3.1",
            ),
            RequiredEvidenceFact(
                source_line=(
                    "memory_embedding_model: str = "
                    '"qwen3-embedding:0.6b"'
                ),
                identifier="memory_embedding_model",
                value="qwen3-embedding:0.6b",
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "Zorunlu değer cevapta eksik",
        ):
            GroundedSynthesisValidator().validate(
                payload=GroundedSynthesisPayload(
                    answer="Ana model llama3.1.",
                    evidence=(
                        'model_name: str = "llama3.1"',
                        (
                            "memory_embedding_model: str = "
                            '"qwen3-embedding:0.6b"'
                        ),
                    ),
                ),
                tool_result=result,
                required_facts=required,
            )

    def test_validator_rejects_invented_technical_value(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "teknik değer kaynakta bulunmuyor",
        ):
            GroundedSynthesisValidator().validate(
                payload=GroundedSynthesisPayload(
                    answer=(
                        "Ana model llama3.1, ayrıca gpt-5.7 kullanılıyor."
                    ),
                    evidence=(
                        'model_name: str = "llama3.1"',
                    ),
                ),
                tool_result=self._config_tool_result(),
            )

    def test_grounded_synthesizer_accepts_complete_two_model_answer(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                (
                    '{"answer":"Ana sohbet modeli llama3.1, '
                    'embedding modeli qwen3-embedding:0.6b.",'
                    '"evidence":['
                    '"model_name: str = \\\"llama3.1\\\"",'
                    '"memory_embedding_model: str = '
                    '\\\"qwen3-embedding:0.6b\\\""]}'
                )
            ]
        )

        answer = GroundedLLMToolResultSynthesizer(
            model
        ).synthesize(
            user_message=(
                "boru/config.py dosyasını oku ve hangi modellerin "
                "kullanıldığını söyle."
            ),
            instruction=(
                "hangi modellerin kullanıldığını söyle"
            ),
            tool_call=ToolCall(
                tool_name="read_file",
                arguments={
                    "path": "boru/config.py",
                },
            ),
            tool_result=self._config_tool_result(),
        )

        self.assertIn(
            "llama3.1",
            answer,
        )
        self.assertIn(
            "qwen3-embedding:0.6b",
            answer,
        )
        self.assertEqual(
            len(model.calls),
            1,
        )

    def test_grounded_synthesizer_repairs_incomplete_first_answer(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                (
                    '{"answer":"Ana model llama3.1.",'
                    '"evidence":['
                    '"model_name: str = \\\"llama3.1\\\""]}'
                ),
                (
                    '{"answer":"Ana model llama3.1, embedding modeli '
                    'qwen3-embedding:0.6b.",'
                    '"evidence":['
                    '"model_name: str = \\\"llama3.1\\\"",'
                    '"memory_embedding_model: str = '
                    '\\\"qwen3-embedding:0.6b\\\""]}'
                ),
            ]
        )

        answer = GroundedLLMToolResultSynthesizer(
            model,
            max_attempts=2,
        ).synthesize(
            user_message=(
                "config.py dosyasını oku ve hangi modellerin "
                "kullanıldığını söyle."
            ),
            instruction=(
                "hangi modellerin kullanıldığını söyle"
            ),
            tool_call=ToolCall(
                tool_name="read_file",
                arguments={"path": "config.py"},
            ),
            tool_result=self._config_tool_result(),
        )

        self.assertIn(
            "qwen3-embedding:0.6b",
            answer,
        )
        self.assertEqual(
            len(model.calls),
            2,
        )
        self.assertIn(
            "Zorunlu kanıt eksik",
            model.calls[1][1].content,
        )

    def test_grounded_synthesizer_falls_back_to_required_facts(
        self,
    ) -> None:
        model = SequenceChatModel(
            [
                "not-json",
                "still-not-json",
            ]
        )

        answer = GroundedLLMToolResultSynthesizer(
            model,
            max_attempts=2,
        ).synthesize(
            user_message=(
                "config.py dosyasını oku ve hangi modellerin "
                "kullanıldığını söyle."
            ),
            instruction=(
                "hangi modellerin kullanıldığını söyle"
            ),
            tool_call=ToolCall(
                tool_name="read_file",
                arguments={"path": "config.py"},
            ),
            tool_result=self._config_tool_result(),
        )

        self.assertIn(
            "model_name: llama3.1",
            answer,
        )
        self.assertIn(
            "memory_embedding_model: qwen3-embedding:0.6b",
            answer,
        )
        self.assertEqual(
            len(model.calls),
            2,
        )

    def test_real_read_file_tool_preserves_grounding_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.py"
            path.write_text(
                (
                    'model_name: str = "llama3.1"\n'
                    'memory_embedding_model: str = '
                    '"qwen3-embedding:0.6b"\n'
                ),
                encoding="utf-8",
            )

            tool_result = ReadFileTool(
                ReadOnlyWorkspace(root)
            ).execute(
                {"path": "config.py"}
            )

            facts = AssignmentRequiredEvidenceExtractor().extract(
                instruction=(
                    "hangi modellerin kullanıldığını söyle"
                ),
                tool_result=tool_result,
            )

            self.assertEqual(
                len(facts),
                2,
            )
            self.assertEqual(
                tool_result.metadata["path"],
                "config.py",
            )


if __name__ == "__main__":
    unittest.main()