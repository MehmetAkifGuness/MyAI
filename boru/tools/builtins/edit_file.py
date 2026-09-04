from boru.tools.arguments import (
    ToolArgumentSchema,
    ToolArgumentSpec,
    ToolArgumentType,
)
from boru.tools.edit_contracts import (
    WorkspaceEditor,
)
from boru.tools.models import (
    ToolResult,
    ToolRisk,
)


class EditFileTool:
    """Önceden hazırlanmış ve hash ile doğrulanmış mevcut dosya güncellemesini uygular."""

    def __init__(
        self,
        workspace: WorkspaceEditor,
    ):
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Workspace içindeki mevcut UTF-8 metin dosyasını, "
            "beklenen SHA-256 kaynağı değişmemişse atomik olarak günceller. "
            "Argümanlar: path, content, expected_sha256."
        )

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.WRITE

    @property
    def argument_schema(
        self,
    ) -> ToolArgumentSchema:
        return ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    name="path",
                    value_type=ToolArgumentType.STRING,
                    required=True,
                    strip=True,
                    allow_empty=False,
                    max_length=1024,
                ),
                ToolArgumentSpec(
                    name="content",
                    value_type=ToolArgumentType.STRING,
                    required=True,
                    strip=False,
                    allow_empty=True,
                    max_length=128 * 1024,
                ),
                ToolArgumentSpec(
                    name="expected_sha256",
                    value_type=ToolArgumentType.STRING,
                    required=True,
                    strip=True,
                    allow_empty=False,
                    max_length=64,
                ),
            )
        )

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        path = arguments.get("path")
        content = arguments.get("content")
        expected_sha256 = arguments.get(
            "expected_sha256"
        )

        if not isinstance(path, str):
            raise ValueError(
                "'path' metin olmalıdır."
            )

        if not isinstance(content, str):
            raise ValueError(
                "'content' metin olmalıdır."
            )

        if not isinstance(
            expected_sha256,
            str,
        ):
            raise ValueError(
                "'expected_sha256' metin olmalıdır."
            )

        if (
            len(expected_sha256) != 64
            or any(
                character not in "0123456789abcdefABCDEF"
                for character in expected_sha256
            )
        ):
            raise ValueError(
                "'expected_sha256' geçerli bir SHA-256 hex değeri olmalıdır."
            )

        outcome = (
            self._workspace
            .apply_text_update(
                relative_path=path,
                content=content,
                expected_sha256=(
                    expected_sha256.casefold()
                ),
            )
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            content=(
                "Dosya güncellendi: "
                f"{outcome.relative_path}"
            ),
            metadata={
                "path": outcome.relative_path,
                "character_count": (
                    outcome.character_count
                ),
                "byte_count": (
                    outcome.byte_count
                ),
            },
        )