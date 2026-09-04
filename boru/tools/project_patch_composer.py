from collections import defaultdict
from collections.abc import Sequence

from boru.tools.diff_renderer import UnifiedDiffRenderer
from boru.tools.edit_models import EditProposal, EditSource
from boru.tools.project_edit_models import ProjectPatchSpec


class GroundedMultiPatchComposer:
    """Bir dosyadaki birden çok exact patch'i çakışmasız tek final edit'e dönüştürür."""

    def __init__(
        self,
        *,
        max_files: int = 4,
        max_patches_per_file: int = 4,
        max_total_patches: int = 12,
        max_patch_characters: int = 24 * 1024,
        diff_renderer: UnifiedDiffRenderer | None = None,
    ):
        if min(
            max_files,
            max_patches_per_file,
            max_total_patches,
            max_patch_characters,
        ) < 1:
            raise ValueError(
                "Multi-patch sınırları en az 1 olmalıdır."
            )

        self._max_files = max_files
        self._max_patches_per_file = (
            max_patches_per_file
        )
        self._max_total_patches = (
            max_total_patches
        )
        self._max_patch_characters = (
            max_patch_characters
        )
        self._diff_renderer = (
            diff_renderer
            or UnifiedDiffRenderer()
        )

    def compose(
        self,
        *,
        patches: Sequence[ProjectPatchSpec],
        source_by_path: dict[str, EditSource],
    ) -> tuple[EditProposal, ...]:
        if not patches:
            raise ValueError(
                "Project edit planner en az bir patch üretmelidir."
            )

        if (
            len(patches)
            > self._max_total_patches
        ):
            raise ValueError(
                "Project edit planner toplam patch sınırını aştı."
            )

        grouped: dict[
            str,
            list[ProjectPatchSpec],
        ] = defaultdict(list)

        total_characters = 0

        for patch in patches:
            if (
                patch.path
                not in source_by_path
            ):
                raise ValueError(
                    "Project edit planner seçilmeyen dosya için patch üretti."
                )

            grouped[
                patch.path
            ].append(
                patch
            )

            total_characters += (
                len(patch.old_text)
                + len(patch.new_text)
            )

        if len(grouped) > self._max_files:
            raise ValueError(
                "Project edit planner izin verilen dosya sayısını aştı."
            )

        if (
            total_characters
            > self._max_patch_characters
        ):
            raise ValueError(
                "Project edit patch toplamı izin verilen boyutu aşıyor."
            )

        edits: list[
            EditProposal
        ] = []

        for (
            path,
            file_patches,
        ) in grouped.items():
            if (
                len(file_patches)
                > self._max_patches_per_file
            ):
                raise ValueError(
                    f"Bir dosyada en fazla "
                    f"{self._max_patches_per_file} patch "
                    f"destekleniyor: {path}"
                )

            source = (
                source_by_path[
                    path
                ]
            )

            updated = (
                self._apply_grounded_non_overlapping(
                    source=source,
                    patches=file_patches,
                )
            )

            diff = (
                self._diff_renderer
                .render(
                    original=(
                        source.content
                    ),
                    updated=updated,
                    fromfile=(
                        f"{path} (mevcut)"
                    ),
                    tofile=(
                        f"{path} (önerilen)"
                    ),
                )
            )

            edits.append(
                EditProposal(
                    path=path,
                    updated_content=(
                        updated
                    ),
                    expected_sha256=(
                        source.sha256
                    ),
                    diff=diff,
                    original_character_count=(
                        len(
                            source.content
                        )
                    ),
                    updated_character_count=(
                        len(updated)
                    ),
                )
            )

        return tuple(
            edits
        )

    @staticmethod
    def _apply_grounded_non_overlapping(
        *,
        source: EditSource,
        patches: Sequence[
            ProjectPatchSpec
        ],
    ) -> str:
        spans: list[
            tuple[
                int,
                int,
                str,
            ]
        ] = []

        preferred_newline = (
            GroundedMultiPatchComposer
            ._preferred_newline(
                source.content
            )
        )

        for patch in patches:
            old_text = patch.old_text
            first = (
                source.content
                .find(
                    old_text
                )
            )

            if (
                first < 0
                and preferred_newline
            ):
                old_text = (
                    GroundedMultiPatchComposer
                    ._normalize_newlines(
                        old_text,
                        preferred_newline,
                    )
                )
                first = source.content.find(
                    old_text
                )

            if first < 0:
                raise ValueError(
                    f"Project patch old_text kaynakta bulunamadı: "
                    f"{patch.path}"
                )

            second = (
                source.content
                .find(
                    old_text,
                    first + 1,
                )
            )

            if second >= 0:
                raise ValueError(
                    f"Project patch old_text birden fazla kez bulundu: "
                    f"{patch.path}"
                )

            spans.append(
                (
                    first,
                    first
                    + len(
                        old_text
                    ),
                    (
                        GroundedMultiPatchComposer
                        ._normalize_newlines(
                            patch.new_text,
                            preferred_newline,
                        )
                        if preferred_newline
                        else patch.new_text
                    ),
                )
            )

        spans.sort(
            key=lambda item: item[0]
        )

        for (
            previous,
            current,
        ) in zip(
            spans,
            spans[1:],
        ):
            if (
                current[0]
                < previous[1]
            ):
                raise ValueError(
                    "Project patch'leri aynı kaynak "
                    "aralığında çakışıyor: "
                    f"{source.path}"
                )

        updated = (
            source.content
        )

        for (
            start,
            end,
            replacement,
        ) in reversed(
            spans
        ):
            updated = (
                updated[:start]
                + replacement
                + updated[end:]
            )

        return updated

    @staticmethod
    def _preferred_newline(
        content: str,
    ) -> str | None:
        without_crlf = content.replace(
            "\r\n",
            "",
        )

        if (
            "\r\n" in content
            and "\n" not in without_crlf
        ):
            return "\r\n"

        if "\n" in content:
            return "\n"

        if "\r" in content:
            return "\r"

        return None

    @staticmethod
    def _normalize_newlines(
        value: str,
        newline: str,
    ) -> str:
        normalized = value.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        return normalized.replace(
            "\n",
            newline,
        )
