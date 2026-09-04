import ast
import re
from collections.abc import Sequence

from boru.tools.edit_contracts import (
    SmartEditWorkspace,
)
from boru.tools.project_edit_contracts import (
    ProjectFileSelector,
)
from boru.tools.project_edit_models import (
    ProjectEditRequest,
    ProjectFileSelection,
)


class DependencyAwareProjectFileSelector:
    """Güvenli manifest içinde yerel Python import ilişkilerini bounded biçimde genişletir."""

    _CUE_PATTERN = re.compile(
        r"\b(?:kullanan|kullanılan|ilgili|bağlı|bagli|bağıml|bagiml|"
        r"uyumlu|entegre|service|servis|controller|test|import|referans)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        base_selector: ProjectFileSelector,
        workspace: SmartEditWorkspace,
        max_files: int = 4,
    ):
        if max_files < 1:
            raise ValueError(
                "max_files en az 1 olmalıdır."
            )

        self._base_selector = (
            base_selector
        )
        self._workspace = (
            workspace
        )
        self._max_files = (
            max_files
        )

    def select_files(
        self,
        *,
        request: ProjectEditRequest,
        available_paths: Sequence[str],
    ) -> ProjectFileSelection:
        base = (
            self._base_selector
            .select_files(
                request=request,
                available_paths=(
                    available_paths
                ),
            )
        )

        if (
            len(base.paths)
            >= self._max_files
            or self._CUE_PATTERN.search(
                request.instruction
            )
            is None
        ):
            return base

        catalog = tuple(
            dict.fromkeys(
                available_paths
            )
        )

        python_catalog = tuple(
            path
            for path in catalog
            if path.endswith(
                ".py"
            )
        )

        module_to_path = (
            self._build_module_index(
                python_catalog
            )
        )

        selected = list(
            base.paths
        )

        selected_set = set(
            selected
        )

        related: list[
            str
        ] = []

        selected_modules = {
            module
            for (
                module,
                path,
            ) in module_to_path.items()
            if path in selected_set
        }

        for path in tuple(
            selected
        ):
            if not path.endswith(
                ".py"
            ):
                continue

            for imported_module in (
                self._read_imports(
                    path
                )
            ):
                candidate = (
                    self._resolve_module_path(
                        imported_module,
                        module_to_path,
                    )
                )

                if (
                    candidate
                    is not None
                    and candidate
                    not in selected_set
                ):
                    related.append(
                        candidate
                    )

        for candidate in (
            python_catalog
        ):
            if (
                candidate
                in selected_set
            ):
                continue

            imports = (
                self._read_imports(
                    candidate
                )
            )

            if any(
                imported
                == selected_module
                or imported.startswith(
                    selected_module
                    + "."
                )
                for imported
                in imports
                for selected_module
                in selected_modules
            ):
                related.append(
                    candidate
                )

        for candidate in sorted(
            dict.fromkeys(
                related
            ),
            key=str.casefold,
        ):
            if (
                len(selected)
                >= self._max_files
            ):
                break

            if (
                candidate
                not in selected_set
            ):
                selected.append(
                    candidate
                )

                selected_set.add(
                    candidate
                )

        return ProjectFileSelection(
            paths=tuple(
                selected
            )
        )

    @staticmethod
    def _build_module_index(
        paths: Sequence[str],
    ) -> dict[str, str]:
        result: dict[
            str,
            str,
        ] = {}

        for path in paths:
            normalized = (
                path.replace(
                    "\\",
                    "/",
                )
            )

            if normalized.endswith(
                "/__init__.py"
            ):
                module = (
                    normalized[
                        : -len(
                            "/__init__.py"
                        )
                    ]
                    .replace(
                        "/",
                        ".",
                    )
                )

            elif normalized.endswith(
                ".py"
            ):
                module = (
                    normalized[:-3]
                    .replace(
                        "/",
                        ".",
                    )
                )

            else:
                continue

            if module:
                result[
                    module
                ] = path

        return result

    def _read_imports(
        self,
        path: str,
    ) -> tuple[str, ...]:
        try:
            source = (
                self._workspace
                .read_edit_source(
                    path
                )
            )

            tree = ast.parse(
                source.content
            )

        except (
            SyntaxError,
            ValueError,
            OSError,
        ):
            return ()

        imports: list[
            str
        ] = []

        for node in ast.walk(
            tree
        ):
            if isinstance(
                node,
                ast.Import,
            ):
                imports.extend(
                    alias.name
                    for alias
                    in node.names
                )

            elif (
                isinstance(
                    node,
                    ast.ImportFrom,
                )
                and node.level == 0
                and node.module
            ):
                imports.append(
                    node.module
                )

        return tuple(
            dict.fromkeys(
                imports
            )
        )

    @staticmethod
    def _resolve_module_path(
        module: str,
        module_to_path: dict[
            str,
            str,
        ],
    ) -> str | None:
        if (
            module
            in module_to_path
        ):
            return (
                module_to_path[
                    module
                ]
            )

        parts = module.split(
            "."
        )

        while len(parts) > 1:
            parts.pop()

            candidate = ".".join(
                parts
            )

            if (
                candidate
                in module_to_path
            ):
                return (
                    module_to_path[
                        candidate
                    ]
                )

        return None