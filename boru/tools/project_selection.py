import re
from collections.abc import Sequence

from boru.tools.project_edit_contracts import (
    ProjectFileSelector,
)
from boru.tools.project_edit_models import (
    ProjectEditRequest,
    ProjectFileSelection,
)


class RuleFirstProjectFileSelector:
    """Açıkça adı verilen manifest dosyalarını deterministik seçer; gerekirse fallback kullanır."""

    _CREATE_ACTION_PATTERN = re.compile(
        r"\b(?:oluştur|olustur|yarat|ekle)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        fallback: ProjectFileSelector,
        max_files: int = 4,
        deterministic_min_paths: int = 2,
    ):
        if max_files < 1:
            raise ValueError(
                "max_files en az 1 olmalıdır."
            )

        if deterministic_min_paths < 1:
            raise ValueError(
                "deterministic_min_paths en az 1 olmalıdır."
            )

        self._fallback = fallback
        self._max_files = max_files
        self._deterministic_min_paths = (
            deterministic_min_paths
        )

    def select_files(
        self,
        *,
        request: ProjectEditRequest,
        available_paths: Sequence[str],
    ) -> ProjectFileSelection:
        catalog = tuple(
            dict.fromkeys(
                path.strip()
                for path in available_paths
                if path.strip()
            )
        )

        explicit_paths = self._extract_explicit_paths(
            instruction=request.instruction,
            catalog=catalog,
        )

        if len(explicit_paths) > self._max_files:
            raise ValueError(
                "Kullanıcı isteğinde açıkça belirtilen dosya sayısı "
                f"izin verilen {self._max_files} sınırını aşıyor."
            )

        if (
            len(explicit_paths)
            >= self._deterministic_min_paths
            or (
                explicit_paths
                and self._CREATE_ACTION_PATTERN.search(
                    request.instruction
                )
            )
        ):
            return ProjectFileSelection(
                paths=explicit_paths
            )

        selection = self._fallback.select_files(
            request=request,
            available_paths=catalog,
        )

        if explicit_paths:
            missing = tuple(
                path
                for path in explicit_paths
                if path not in selection.paths
            )

            if missing:
                raise ValueError(
                    "Project planner kullanıcı tarafından açıkça belirtilen "
                    "dosyaları seçmedi."
                )

        return selection

    @staticmethod
    def _extract_explicit_paths(
        *,
        instruction: str,
        catalog: Sequence[str],
    ) -> tuple[str, ...]:
        normalized_instruction = instruction.replace(
            "\\",
            "/",
        )

        matches: list[tuple[int, str]] = []

        for path in catalog:
            normalized_path = path.replace(
                "\\",
                "/",
            )

            pattern = re.compile(
                rf"(?<![\w./-]){re.escape(normalized_path)}(?![\w./-])",
                re.IGNORECASE,
            )

            match = pattern.search(
                normalized_instruction
            )

            if match is None:
                continue

            matches.append(
                (
                    match.start(),
                    path,
                )
            )

        matches.sort(
            key=lambda item: item[0]
        )

        return tuple(
            path
            for _, path in matches
        )
