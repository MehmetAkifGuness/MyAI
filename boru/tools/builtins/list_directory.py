from boru.tools.arguments import (
    ToolArgumentSchema,
    ToolArgumentSpec,
    ToolArgumentType,
)
from boru.tools.models import (
    ToolResult,
    ToolRisk,
)
from boru.tools.contracts import (
    WorkspaceReader,
)


class ListDirectoryTool:
    """İzin verilen workspace içindeki klasör içeriğini listeler."""

    def __init__(
        self,
        workspace: WorkspaceReader,
    ):
        self._workspace = (
            workspace
        )

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(
        self,
    ) -> str:
        return (
            "İzin verilen proje "
            "workspace'i içindeki "
            "bir klasörün dosya ve "
            "alt klasörlerini listeler. "
            "Argüman: path "
            "(workspace-relative metin; "
            "proje kökü için .)."
        )

    @property
    def risk(
        self,
    ) -> ToolRisk:
        return (
            ToolRisk.READ_ONLY
        )

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
                    required=False,
                    strip=True,
                    allow_empty=True,
                    max_length=1024,
                    has_default=True,
                    default=".",
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
        unexpected = (
            set(arguments)
            - {"path"}
        )

        if unexpected:
            raise ValueError(
                "list_directory yalnızca "
                "'path' argümanını kabul eder."
            )

        raw_path = arguments.get(
            "path",
            ".",
        )

        if not isinstance(
            raw_path,
            str,
        ):
            raise ValueError(
                "'path' metin olmalıdır."
            )

        relative_path = (
            raw_path.strip()
            or "."
        )

        listing = (
            self
            ._workspace
            .list_directory(
                relative_path
            )
        )

        display_path = (
            "proje kökü"
            if relative_path == "."
            else relative_path
        )

        entry_count = (
            listing.total_entries
            if (
                listing.total_entries
                is not None
            )
            else len(
                listing.entries
            )
        )

        lines = [
            f"Klasör: {display_path}",
            f"Toplam öğe: {entry_count}",
        ]

        if not listing.entries:
            lines.append(
                "(boş klasör)"
            )

        else:
            for entry in (
                listing.entries
            ):
                kind = (
                    "DIR"
                    if (
                        entry
                        .is_directory
                    )
                    else "FILE"
                )

                lines.append(
                    f"[{kind}] "
                    f"{entry.relative_path}"
                )

        if listing.truncated:
            lines.append(
                "(liste güvenlik limiti "
                "nedeniyle kısaltıldı)"
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            content="\n".join(
                lines
            ),
            metadata={
                "path": relative_path,
                "display_path": (
                    display_path
                ),
                "entry_count": (
                    entry_count
                ),
                "truncated": (
                    listing.truncated
                ),
            },
        )