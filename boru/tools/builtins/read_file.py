from boru.tools.models import (
    ToolResult,
    ToolRisk,
)
from boru.tools.contracts import (
    WorkspaceReader,
)


class ReadFileTool:
    """İzin verilen workspace içindeki UTF-8 metin dosyalarını okur."""

    def __init__(
        self,
        workspace: WorkspaceReader,
    ):
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "İzin verilen proje workspace'i içindeki "
            "küçük bir UTF-8 metin dosyasını okur."
        )

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.READ_ONLY

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        unexpected = set(arguments) - {"path"}
        if unexpected:
            raise ValueError(
                "read_file yalnızca 'path' argümanını kabul eder."
            )

        raw_path = arguments.get("path")

        if not isinstance(raw_path, str):
            raise ValueError(
                "read_file için 'path' metin olmalıdır."
            )

        relative_path = raw_path.strip()
        if not relative_path:
            raise ValueError(
                "Okunacak dosya yolu boş olamaz."
            )

        content = self._workspace.read_text_file(
            relative_path
        )

        rendered_content = (
            content
            if content
            else "(boş dosya)"
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            content=(
                f"Dosya: {relative_path}\n"
                f"{rendered_content}"
            ),
            metadata={
                "path": relative_path,
                "character_count": len(content),
            },
        )