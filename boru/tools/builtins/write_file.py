from boru.tools.arguments import (
    ToolArgumentSchema,
    ToolArgumentSpec,
    ToolArgumentType,
)
from boru.tools.models import (
    ToolResult,
    ToolRisk,
)
from boru.tools.write_contracts import (
    WorkspaceWriter,
)


class WriteFileTool:
    """Workspace içinde yalnızca yeni bir UTF-8 metin dosyası oluşturur."""

    def __init__(
        self,
        workspace: WorkspaceWriter,
    ):
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(
        self,
    ) -> str:
        return (
            "İzin verilen workspace içinde yeni bir UTF-8 metin dosyası oluşturur. "
            "Mevcut dosyanın üzerine yazmaz. "
            "Argümanlar: path ve content."
        )

    @property
    def risk(
        self,
    ) -> ToolRisk:
        return ToolRisk.WRITE

    @property
    def argument_schema(
        self,
    ) -> ToolArgumentSchema:
        return ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    name="path",
                    value_type=(
                        ToolArgumentType.STRING
                    ),
                    required=True,
                    strip=True,
                    allow_empty=False,
                    max_length=1024,
                ),
                ToolArgumentSpec(
                    name="content",
                    value_type=(
                        ToolArgumentType.STRING
                    ),
                    required=True,
                    strip=False,
                    allow_empty=True,
                    max_length=128 * 1024,
                ),
            )
        )

    def execute(
        self,
        arguments: dict[
            str,
            object,
        ],
    ) -> ToolResult:
        path = arguments.get(
            "path"
        )

        content = arguments.get(
            "content"
        )

        if not isinstance(
            path,
            str,
        ):
            raise ValueError(
                "'path' metin olmalıdır."
            )

        if not isinstance(
            content,
            str,
        ):
            raise ValueError(
                "'content' metin olmalıdır."
            )

        outcome = (
            self._workspace
            .write_text_file(
                path,
                content,
            )
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            content=(
                "Dosya oluşturuldu: "
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