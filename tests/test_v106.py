import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from boru.models import ChatMessage
from boru.tools import (
    CalculatorTool,
    CurrentTimeTool,
    LLMToolPlanner,
    ListDirectoryTool,
    ReadFileTool,
    ReadOnlyWorkspace,
    RiskBasedToolPolicy,
    ToolArgumentSchema,
    ToolArgumentSpec,
    ToolArgumentType,
    ToolArgumentValidationError,
    ToolArgumentValidator,
    ToolCall,
    ToolExecutor,
    ToolRegistry,
    ToolResult,
    ToolRisk,
)


class ProbeTool:
    def __init__(
        self,
        schema: ToolArgumentSchema,
    ):
        self._schema = schema
        self.calls: list[dict[str, object]] = []

    @property
    def name(self) -> str:
        return "probe"

    @property
    def description(self) -> str:
        return "Argument validation probe."

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.SAFE

    @property
    def argument_schema(self) -> ToolArgumentSchema:
        return self._schema

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        self.calls.append(dict(arguments))

        return ToolResult(
            tool_name=self.name,
            success=True,
            content="ok",
        )


class LegacyNoSchemaTool:
    def __init__(self):
        self.calls = 0

    @property
    def name(self) -> str:
        return "legacy"

    @property
    def description(self) -> str:
        return "Legacy no-schema tool."

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.SAFE

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        self.calls += 1

        return ToolResult(
            tool_name=self.name,
            success=True,
            content=str(arguments),
        )


class RecordingChatModel:
    def __init__(
        self,
        response: str,
    ):
        self._response = response
        self.calls: list[
            list[ChatMessage]
        ] = []

    def generate(
        self,
        messages: Sequence[
            ChatMessage
        ],
    ) -> str:
        self.calls.append(
            list(messages)
        )

        return self._response


class CentralToolArgumentValidationTests(
    unittest.TestCase
):
    def test_validator_normalizes_required_string(
        self,
    ) -> None:
        validator = (
            ToolArgumentValidator()
        )

        schema = ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    name="path",
                    value_type=(
                        ToolArgumentType.STRING
                    ),
                    strip=True,
                    allow_empty=False,
                ),
            )
        )

        result = validator.validate(
            schema,
            {
                "path": (
                    "  boru/config.py  "
                )
            },
        )

        self.assertEqual(
            result,
            {
                "path": (
                    "boru/config.py"
                )
            },
        )

    def test_validator_rejects_unknown_argument(
        self,
    ) -> None:
        validator = (
            ToolArgumentValidator()
        )

        schema = (
            ToolArgumentSchema()
        )

        with self.assertRaisesRegex(
            ToolArgumentValidationError,
            "Beklenmeyen",
        ):
            validator.validate(
                schema,
                {
                    "unexpected": True
                },
            )

    def test_validator_rejects_missing_required_argument(
        self,
    ) -> None:
        schema = ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    name="expression",
                    value_type=(
                        ToolArgumentType.STRING
                    ),
                ),
            )
        )

        with self.assertRaisesRegex(
            ToolArgumentValidationError,
            "Zorunlu",
        ):
            ToolArgumentValidator().validate(
                schema,
                {},
            )

    def test_validator_rejects_wrong_type(
        self,
    ) -> None:
        schema = ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    name="path",
                    value_type=(
                        ToolArgumentType.STRING
                    ),
                ),
            )
        )

        with self.assertRaisesRegex(
            ToolArgumentValidationError,
            "metin",
        ):
            ToolArgumentValidator().validate(
                schema,
                {
                    "path": 123
                },
            )

    def test_validator_applies_and_normalizes_default(
        self,
    ) -> None:
        schema = ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    name="path",
                    value_type=(
                        ToolArgumentType.STRING
                    ),
                    required=False,
                    strip=True,
                    has_default=True,
                    default="  .  ",
                ),
            )
        )

        result = (
            ToolArgumentValidator()
            .validate(
                schema,
                {},
            )
        )

        self.assertEqual(
            result,
            {
                "path": "."
            },
        )

    def test_validator_enforces_string_length_limit(
        self,
    ) -> None:
        schema = ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    name="path",
                    value_type=(
                        ToolArgumentType.STRING
                    ),
                    max_length=4,
                ),
            )
        )

        with self.assertRaisesRegex(
            ToolArgumentValidationError,
            "en fazla 4",
        ):
            ToolArgumentValidator().validate(
                schema,
                {
                    "path": "12345"
                },
            )

    def test_executor_validates_before_tool_execution(
        self,
    ) -> None:
        tool = ProbeTool(
            ToolArgumentSchema(
                arguments=(
                    ToolArgumentSpec(
                        name="path",
                        value_type=(
                            ToolArgumentType.STRING
                        ),
                        strip=True,
                        allow_empty=False,
                    ),
                )
            )
        )

        executor = ToolExecutor(
            registry=ToolRegistry(
                [tool]
            ),
            policy=(
                RiskBasedToolPolicy()
            ),
        )

        result = executor.execute(
            ToolCall(
                tool_name="probe",
                arguments={
                    "path": 123
                },
            )
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "Tool argümanları geçersiz",
            result.error or "",
        )

        self.assertEqual(
            tool.calls,
            [],
        )

    def test_executor_passes_normalized_arguments_to_tool(
        self,
    ) -> None:
        tool = ProbeTool(
            ToolArgumentSchema(
                arguments=(
                    ToolArgumentSpec(
                        name="path",
                        value_type=(
                            ToolArgumentType.STRING
                        ),
                        strip=True,
                        allow_empty=False,
                    ),
                )
            )
        )

        executor = ToolExecutor(
            registry=ToolRegistry(
                [tool]
            ),
            policy=(
                RiskBasedToolPolicy()
            ),
        )

        result = executor.execute(
            ToolCall(
                tool_name="probe",
                arguments={
                    "path": (
                        "  tests  "
                    )
                },
            )
        )

        self.assertTrue(
            result.success
        )

        self.assertEqual(
            tool.calls,
            [
                {
                    "path": "tests"
                }
            ],
        )

    def test_legacy_tool_without_schema_is_no_argument_by_default(
        self,
    ) -> None:
        tool = (
            LegacyNoSchemaTool()
        )

        executor = ToolExecutor(
            registry=ToolRegistry(
                [tool]
            ),
            policy=(
                RiskBasedToolPolicy()
            ),
        )

        result = executor.execute(
            ToolCall(
                tool_name="legacy",
                arguments={
                    "dangerous": (
                        "value"
                    )
                },
            )
        )

        self.assertFalse(
            result.success
        )

        self.assertEqual(
            tool.calls,
            0,
        )

    def test_calculator_schema_rejects_extra_argument_centrally(
        self,
    ) -> None:
        executor = ToolExecutor(
            registry=ToolRegistry(
                [
                    CalculatorTool()
                ]
            ),
            policy=(
                RiskBasedToolPolicy()
            ),
        )

        result = executor.execute(
            ToolCall(
                tool_name=(
                    "calculator"
                ),
                arguments={
                    "expression": (
                        "2 + 2"
                    ),
                    "extra": "x",
                },
            )
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            (
                "Beklenmeyen tool "
                "argümanı: extra"
            ),
            result.error or "",
        )

    def test_current_time_schema_rejects_any_argument(
        self,
    ) -> None:
        executor = ToolExecutor(
            registry=ToolRegistry(
                [
                    CurrentTimeTool()
                ]
            ),
            policy=(
                RiskBasedToolPolicy()
            ),
        )

        result = executor.execute(
            ToolCall(
                tool_name=(
                    "get_current_time"
                ),
                arguments={
                    "timezone": "UTC"
                },
            )
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "Beklenmeyen tool argümanı",
            result.error or "",
        )

    def test_list_directory_schema_applies_root_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "a.txt"
            ).write_text(
                "a",
                encoding="utf-8",
            )

            executor = ToolExecutor(
                registry=ToolRegistry(
                    [
                        ListDirectoryTool(
                            ReadOnlyWorkspace(
                                root
                            )
                        )
                    ]
                ),
                policy=(
                    RiskBasedToolPolicy(
                        allowed_risks=(
                            ToolRisk.READ_ONLY,
                        )
                    )
                ),
            )

            result = executor.execute(
                ToolCall(
                    tool_name=(
                        "list_directory"
                    )
                )
            )

            self.assertTrue(
                result.success
            )

            self.assertEqual(
                result.metadata[
                    "path"
                ],
                ".",
            )

    def test_read_file_schema_strips_path_before_workspace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )

            (
                root
                / "note.txt"
            ).write_text(
                "hello",
                encoding="utf-8",
            )

            executor = ToolExecutor(
                registry=ToolRegistry(
                    [
                        ReadFileTool(
                            ReadOnlyWorkspace(
                                root
                            )
                        )
                    ]
                ),
                policy=(
                    RiskBasedToolPolicy(
                        allowed_risks=(
                            ToolRisk.READ_ONLY,
                        )
                    )
                ),
            )

            result = executor.execute(
                ToolCall(
                    tool_name=(
                        "read_file"
                    ),
                    arguments={
                        "path": (
                            "  note.txt  "
                        ),
                    },
                )
            )

            self.assertTrue(
                result.success
            )

            self.assertEqual(
                result.metadata[
                    "path"
                ],
                "note.txt",
            )

    def test_registry_exposes_structured_argument_schema(
        self,
    ) -> None:
        definition = (
            ToolRegistry(
                [
                    ReadFileTool(
                        ReadOnlyWorkspace(
                            "."
                        )
                    )
                ]
            )
            .definitions()[0]
        )

        self.assertEqual(
            len(
                definition.arguments
            ),
            1,
        )

        self.assertEqual(
            definition.arguments[
                0
            ].name,
            "path",
        )

        self.assertEqual(
            definition.arguments[
                0
            ].value_type,
            ToolArgumentType.STRING,
        )

        self.assertTrue(
            definition.arguments[
                0
            ].required
        )

    def test_llm_planner_catalog_contains_structured_argument_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = (
                RecordingChatModel(
                    (
                        '{"should_use_tool":false,'
                        '"tool_name":null,'
                        '"arguments":{},'
                        '"response_mode":"direct",'
                        '"synthesis_instruction":"",'
                        '"reason":"gerek yok"}'
                    )
                )
            )

            registry = ToolRegistry(
                [
                    ReadFileTool(
                        ReadOnlyWorkspace(
                            directory
                        )
                    )
                ]
            )

            LLMToolPlanner(
                chat_model=model,
                registry=registry,
            ).plan(
                "dosyaya bak"
            )

            prompt = (
                model
                .calls[0][1]
                .content
            )

            self.assertIn(
                (
                    "args="
                    "path:string(required)"
                ),
                prompt,
            )


if __name__ == "__main__":
    unittest.main()