import hashlib
from dataclasses import dataclass
from typing import Protocol

from boru.tools.edit_models import (
    EditOutcome,
    EditSource,
)
from boru.tools.project_edit_models import (
    ProjectEditOutcome,
    ProjectEditProposal,
)
from boru.tools.write_models import WriteOutcome


class ProjectTransactionWorkspace(Protocol):
    def read_edit_source(
        self,
        relative_path: str,
    ) -> EditSource:
        ...

    def apply_text_update(
        self,
        *,
        relative_path: str,
        content: str,
        expected_sha256: str,
    ) -> EditOutcome:
        ...


class ProjectCreationWorkspace(Protocol):
    def validate_new_text_file(
        self,
        relative_path: str,
        content: str,
    ) -> None:
        ...

    def write_text_file(
        self,
        relative_path: str,
        content: str,
    ) -> WriteOutcome:
        ...

    def remove_created_text_file(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class _CommittedEdit:
    path: str
    original_content: str
    committed_sha256: str


@dataclass(frozen=True, slots=True)
class _CommittedCreation:
    path: str
    committed_sha256: str


class BatchProjectEditApplier:
    """Tüm hash'leri önce doğrular; hata olursa uygulanmış editleri güvenli biçimde geri alır."""

    def __init__(
        self,
        *,
        workspace: ProjectTransactionWorkspace,
        creation_workspace: ProjectCreationWorkspace | None = None,
    ):
        self._workspace = workspace
        self._creation_workspace = creation_workspace

    def apply_project_edit(
        self,
        proposal: ProjectEditProposal,
    ) -> ProjectEditOutcome:
        originals = self._preflight(
            proposal
        )

        committed: list[
            _CommittedEdit | _CommittedCreation
        ] = []
        outcomes: list[
            EditOutcome | WriteOutcome
        ] = []

        try:
            for edit in proposal.edits:
                outcome = (
                    self._workspace
                    .apply_text_update(
                        relative_path=edit.path,
                        content=(
                            edit.updated_content
                        ),
                        expected_sha256=(
                            edit.expected_sha256
                        ),
                    )
                )

                committed_source = (
                    self._workspace
                    .read_edit_source(
                        edit.path
                    )
                )

                committed.append(
                    _CommittedEdit(
                        path=edit.path,
                        original_content=(
                            originals[
                                edit.path
                            ].content
                        ),
                        committed_sha256=(
                            committed_source.sha256
                        ),
                    )
                )

                outcomes.append(
                    outcome
                )

            for creation in proposal.creations:
                creation_workspace = self._require_creation_workspace()
                outcome = creation_workspace.write_text_file(
                    creation.path,
                    creation.content,
                )

                committed.append(
                    _CommittedCreation(
                        path=creation.path,
                        committed_sha256=hashlib.sha256(
                            creation.content.encode(
                                "utf-8"
                            )
                        ).hexdigest(),
                    )
                )
                outcomes.append(
                    outcome
                )

        except Exception as error:
            rollback_error = self._rollback(
                committed
            )

            if rollback_error is not None:
                raise RuntimeError(
                    "Toplu düzenleme başarısız oldu ve otomatik geri alma "
                    "tamamlanamadı. Dosyaları manuel kontrol et. "
                    f"Asıl hata: {error}; rollback hatası: {rollback_error}"
                ) from error

            raise RuntimeError(
                "Toplu düzenleme uygulanamadı; daha önce uygulanmış değişiklikler geri alındı. "
                f"Neden: {error}"
            ) from error

        return ProjectEditOutcome(
            outcomes=tuple(outcomes)
        )

    def _preflight(
        self,
        proposal: ProjectEditProposal,
    ) -> dict[str, EditSource]:
        originals: dict[
            str,
            EditSource,
        ] = {}

        for edit in proposal.edits:
            current = (
                self._workspace
                .read_edit_source(
                    edit.path
                )
            )

            if (
                current.sha256
                != edit.expected_sha256
            ):
                raise ValueError(
                    "Proje dosyalarından biri önizlemeden sonra değişmiş. "
                    "Hiçbir toplu değişiklik uygulanmadı."
                )

            originals[
                edit.path
            ] = current

        for creation in proposal.creations:
            self._require_creation_workspace().validate_new_text_file(
                creation.path,
                creation.content,
            )

        return originals

    def _require_creation_workspace(
        self,
    ) -> ProjectCreationWorkspace:
        if self._creation_workspace is None:
            raise ValueError(
                "Project transaction yeni dosya oluşturma workspace'i içermiyor."
            )

        return self._creation_workspace

    def _rollback(
        self,
        committed: list[
            _CommittedEdit | _CommittedCreation
        ],
    ) -> Exception | None:
        first_error: Exception | None = None

        for item in reversed(
            committed
        ):
            try:
                if isinstance(
                    item,
                    _CommittedCreation,
                ):
                    self._require_creation_workspace().remove_created_text_file(
                        item.path,
                        expected_sha256=(
                            item.committed_sha256
                        ),
                    )
                    continue

                current = (
                    self._workspace
                    .read_edit_source(
                        item.path
                    )
                )

                if (
                    current.sha256
                    != item.committed_sha256
                ):
                    raise RuntimeError(
                        "Rollback hedefi toplu işlemden sonra dışarıdan değişmiş; "
                        "harici değişiklik korunmak için üzerine yazılmadı."
                    )

                self._workspace.apply_text_update(
                    relative_path=item.path,
                    content=(
                        item.original_content
                    ),
                    expected_sha256=(
                        item.committed_sha256
                    ),
                )
            except Exception as error:
                if first_error is None:
                    first_error = error

        return first_error
