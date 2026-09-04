from threading import RLock

from boru.tools.contracts import (
    ToolExecutorPort,
)
from boru.tools.edit_contracts import (
    EditProposalPreparer,
    EditRequestParser,
    SmartEditProposalPreparer,
    SmartEditRequestParser,
)
from boru.tools.edit_models import (
    EditProposal,
)
from boru.tools.models import (
    ToolCall,
)
from boru.tools.project_edit_contracts import (
    ProjectEditApplier,
    ProjectEditProposalPreparer,
    ProjectEditRequestParser,
)
from boru.tools.project_edit_models import (
    ProjectEditProposal,
)
from boru.tools.write_contracts import (
    WriteIntentDetector,
    WriteRequestParser,
)
from boru.tools.write_models import (
    WriteRequest,
)


class ControlledWriteCoordinator:
    """Create/edit/project-edit isteklerini önizler ve yalnızca açık onaydan sonra uygular."""

    _APPROVE_COMMANDS = {
        "onayla",
        "yazmayı onayla",
        "dosya yazımını onayla",
        "değişikliği onayla",
        "düzenlemeyi onayla",
        "proje değişikliğini onayla",
    }

    _CANCEL_COMMANDS = {
        "iptal",
        "vazgeç",
        "yazmayı iptal et",
        "değişikliği iptal et",
        "düzenlemeyi iptal et",
        "proje değişikliğini iptal et",
    }

    def __init__(
        self,
        *,
        parser: WriteRequestParser,
        intent_detector: WriteIntentDetector,
        executor: ToolExecutorPort,
        edit_parser: EditRequestParser | None = None,
        edit_preparer: EditProposalPreparer | None = None,
        smart_edit_parser: SmartEditRequestParser | None = None,
        smart_edit_preparer: SmartEditProposalPreparer | None = None,
        project_edit_parser: ProjectEditRequestParser | None = None,
        project_edit_preparer: ProjectEditProposalPreparer | None = None,
        project_edit_applier: ProjectEditApplier | None = None,
        preview_characters: int = 6000,
    ):
        if preview_characters < 1:
            raise ValueError(
                "preview_characters en az 1 olmalıdır."
            )

        if (
            (edit_parser is None)
            != (edit_preparer is None)
        ):
            raise ValueError(
                "edit_parser ve edit_preparer birlikte verilmelidir."
            )

        if (
            (smart_edit_parser is None)
            != (smart_edit_preparer is None)
        ):
            raise ValueError(
                "smart_edit_parser ve smart_edit_preparer birlikte verilmelidir."
            )

        project_parts = (
            project_edit_parser,
            project_edit_preparer,
            project_edit_applier,
        )

        if any(
            item is not None
            for item in project_parts
        ) and not all(
            item is not None
            for item in project_parts
        ):
            raise ValueError(
                "project_edit_parser, project_edit_preparer ve project_edit_applier birlikte verilmelidir."
            )

        self._parser = parser
        self._intent_detector = intent_detector
        self._executor = executor
        self._edit_parser = edit_parser
        self._edit_preparer = edit_preparer
        self._smart_edit_parser = smart_edit_parser
        self._smart_edit_preparer = smart_edit_preparer
        self._project_edit_parser = project_edit_parser
        self._project_edit_preparer = project_edit_preparer
        self._project_edit_applier = project_edit_applier
        self._preview_characters = preview_characters
        self._pending: (
            WriteRequest
            | EditProposal
            | ProjectEditProposal
            | None
        ) = None
        self._lock = RLock()

    def resolve(
        self,
        user_message: str,
    ) -> str | None:
        normalized = self._normalize_command(
            user_message
        )

        with self._lock:
            if (
                self._pending is not None
                and normalized in self._APPROVE_COMMANDS
            ):
                pending = self._pending
                self._pending = None

                return self._execute_pending(
                    pending
                )

            if (
                self._pending is not None
                and normalized in self._CANCEL_COMMANDS
            ):
                self._pending = None

                return (
                    "Bekleyen dosya değişikliği iptal edildi."
                )

            if self._pending is not None:
                return self._pending_message()

            edit_response = self._try_stage_edit(
                user_message
            )

            if edit_response is not None:
                return edit_response

            project_response = self._try_stage_project_edit(
                user_message
            )

            if project_response is not None:
                return project_response

            smart_edit_response = self._try_stage_smart_edit(
                user_message
            )

            if smart_edit_response is not None:
                return smart_edit_response

            request = self._parser.parse(
                user_message
            )

            if request is not None:
                if self._pending is not None:
                    return self._pending_message()

                self._pending = request

                return self._render_create_preview(
                    request
                )

            if self._intent_detector.is_write_intent(
                user_message
            ):
                if self._pending is not None:
                    return self._pending_message()

                return self._render_usage_guidance()

        return None

    def _try_stage_edit(
        self,
        user_message: str,
    ) -> str | None:
        if (
            self._edit_parser is None
            or self._edit_preparer is None
        ):
            return None

        try:
            request = self._edit_parser.parse(
                user_message
            )
        except Exception as error:
            return (
                "Düzenleme isteği geçersiz: "
                f"{error}"
            )

        if request is None:
            return None

        if self._pending is not None:
            return self._pending_message()

        try:
            proposal = (
                self._edit_preparer
                .prepare_exact_replacement(
                    request
                )
            )
        except Exception as error:
            return (
                "Düzenleme hazırlanamadı: "
                f"{error}"
            )

        self._pending = proposal

        return self._render_edit_preview(
            proposal
        )

    def _try_stage_project_edit(
        self,
        user_message: str,
    ) -> str | None:
        if (
            self._project_edit_parser is None
            or self._project_edit_preparer is None
        ):
            return None

        try:
            request = self._project_edit_parser.parse(
                user_message
            )
        except Exception as error:
            return (
                "Proje düzenleme isteği geçersiz: "
                f"{error}"
            )

        if request is None:
            return None

        if self._pending is not None:
            return self._pending_message()

        try:
            proposal = (
                self._project_edit_preparer
                .prepare_project_edit(
                    request
                )
            )
        except Exception as error:
            return (
                "Proje düzenleme hazırlanamadı: "
                f"{error}"
            )

        self._pending = proposal

        return self._render_project_edit_preview(
            proposal
        )

    def _try_stage_smart_edit(
        self,
        user_message: str,
    ) -> str | None:
        if (
            self._smart_edit_parser is None
            or self._smart_edit_preparer is None
        ):
            return None

        try:
            request = self._smart_edit_parser.parse(
                user_message
            )
        except Exception as error:
            return (
                "Akıllı düzenleme isteği geçersiz: "
                f"{error}"
            )

        if request is None:
            return None

        if self._pending is not None:
            return self._pending_message()

        try:
            proposal = (
                self._smart_edit_preparer
                .prepare_smart_edit(
                    request
                )
            )
        except Exception as error:
            return (
                "Akıllı düzenleme hazırlanamadı: "
                f"{error}"
            )

        self._pending = proposal

        return self._render_edit_preview(
            proposal
        )

    def _execute_pending(
        self,
        pending: (
            WriteRequest
            | EditProposal
            | ProjectEditProposal
        ),
    ) -> str:
        if isinstance(
            pending,
            WriteRequest,
        ):
            return self._execute_create(
                pending
            )

        if isinstance(
            pending,
            ProjectEditProposal,
        ):
            return self._execute_project_edit(
                pending
            )

        return self._execute_edit(
            pending
        )

    def _execute_create(
        self,
        request: WriteRequest,
    ) -> str:
        result = self._executor.execute(
            ToolCall(
                tool_name="write_file",
                arguments={
                    "path": request.path,
                    "content": request.content,
                },
            )
        )

        if not result.success:
            return (
                "Dosya yazma işlemi uygulanamadı: "
                f"{result.error}"
            )

        return result.content.strip()

    def _execute_edit(
        self,
        proposal: EditProposal,
    ) -> str:
        result = self._executor.execute(
            ToolCall(
                tool_name="edit_file",
                arguments={
                    "path": proposal.path,
                    "content": proposal.updated_content,
                    "expected_sha256": (
                        proposal.expected_sha256
                    ),
                },
            )
        )

        if not result.success:
            return (
                "Dosya düzenleme işlemi uygulanamadı: "
                f"{result.error}"
            )

        return result.content.strip()

    def _execute_project_edit(
        self,
        proposal: ProjectEditProposal,
    ) -> str:
        if self._project_edit_applier is None:
            return (
                "Proje düzenleme applier yapılandırılmamış."
            )

        try:
            outcome = (
                self._project_edit_applier
                .apply_project_edit(
                    proposal
                )
            )
        except Exception as error:
            return (
                "Proje düzenleme işlemi uygulanamadı: "
                f"{error}"
            )

        paths = "\n".join(
            f"- {item.relative_path}"
            for item in outcome.outcomes
        )

        return (
            "Proje düzenlemesi uygulandı: "
            f"{len(outcome.outcomes)} dosya\n"
            f"{paths}"
        )

    def _render_create_preview(
        self,
        request: WriteRequest,
    ) -> str:
        preview = request.content[
            : self._preview_characters
        ]

        truncated = (
            len(request.content)
            > self._preview_characters
        )

        suffix = (
            "\n... (önizleme kısaltıldı)"
            if truncated
            else ""
        )

        return (
            "Yazma işlemi hazırlandı ancak henüz uygulanmadı.\n"
            f"Hedef: {request.path}\n"
            f"Karakter: {len(request.content)}\n"
            "Mod: yalnızca yeni dosya oluşturma; mevcut dosyanın üzerine yazılmaz.\n"
            "Önizleme:\n"
            f"{preview}"
            f"{suffix}\n\n"
            "Uygulamak için yalnızca 'onayla', vazgeçmek için 'iptal' yaz."
        )

    def _render_edit_preview(
        self,
        proposal: EditProposal,
    ) -> str:
        diff_preview = proposal.diff[
            : self._preview_characters
        ]

        truncated = (
            len(proposal.diff)
            > self._preview_characters
        )

        suffix = (
            "\n... (diff önizlemesi kısaltıldı)"
            if truncated
            else ""
        )

        return (
            "Düzenleme hazırlandı ancak henüz uygulanmadı.\n"
            f"Hedef: {proposal.path}\n"
            "Mod: mevcut dosyada tek ve tam eşleşen içerik değiştirme.\n"
            f"Karakter: {proposal.original_character_count} → "
            f"{proposal.updated_character_count}\n"
            "Dosya onaydan önce değişirse işlem otomatik iptal edilir.\n"
            "Diff:\n"
            f"{diff_preview}"
            f"{suffix}\n\n"
            "Uygulamak için yalnızca 'onayla', vazgeçmek için 'iptal' yaz."
        )

    def _render_project_edit_preview(
        self,
        proposal: ProjectEditProposal,
    ) -> str:
        sections = [
            (
                f"===== {edit.path} =====\n"
                f"{edit.diff.rstrip()}"
            )
            for edit in proposal.edits
        ]

        sections.extend(
            (
                f"===== CREATE {creation.path} =====\n"
                f"{creation.content}"
            )
            for creation in proposal.creations
        )

        combined_diff = "\n".join(
            sections
        )

        diff_preview = combined_diff[
            : self._preview_characters
        ]

        truncated = (
            len(combined_diff)
            > self._preview_characters
        )

        suffix = (
            "\n... (toplu diff önizlemesi kısaltıldı)"
            if truncated
            else ""
        )

        paths = ", ".join(
            [
                edit.path
                for edit in proposal.edits
            ]
            + [
                creation.path
                for creation in proposal.creations
            ]
        )

        file_count = (
            len(proposal.edits)
            + len(proposal.creations)
        )

        return (
            "Proje düzenlemesi hazırlandı ancak henüz uygulanmadı.\n"
            f"Dosya sayısı: {file_count}\n"
            f"Düzenleme: {len(proposal.edits)}, "
            f"yeni dosya: {len(proposal.creations)}\n"
            f"Hedefler: {paths}\n"
            "Mod: grounded edit + güvenli create; tek onayla transaction.\n"
            "Mevcut hedef değişirse veya yeni hedef oluşturulursa hiçbir işlem uygulanmaz.\n"
            "Toplu diff:\n"
            f"{diff_preview}"
            f"{suffix}\n\n"
            "Tüm değişiklikleri uygulamak için 'onayla', vazgeçmek için 'iptal' yaz."
        )

    def _render_usage_guidance(
        self,
    ) -> str:
        if self._edit_parser is None:
            return (
                "Bu sürüm kontrollü olarak yalnızca tam içerik verilen "
                "yeni dosya oluşturma işlemini destekliyor. "
                "Örnek biçim:\n"
                "dosya oluştur: notes/ornek.txt\n"
                "İçerik:\n"
                "Merhaba Börü"
            )

        if self._smart_edit_parser is None:
            return (
                "Kontrollü dosya oluşturma ve exact-replace düzenleme destekleniyor.\n"
                "Yeni dosya örneği:\n"
                "dosya oluştur: notes/ornek.txt\n"
                "İçerik:\n"
                "Merhaba Börü\n\n"
                "Mevcut dosya düzenleme örneği:\n"
                "dosya düzenle: boru/config.py\n"
                "Eski:\n"
                "model_name: str = \"llama3.1\"\n"
                "Yeni:\n"
                "model_name: str = \"llama3.2\""
            )

        project_guidance = ""

        if self._project_edit_parser is not None:
            project_guidance = (
                "\n\nProject-aware toplu düzenleme örneği:\n"
                "proje düzenle: config ayarını güncelle ve bu ayarı kullanan ilgili servisi de uyumlu hale getir"
            )

        return (
            "Kontrollü dosya oluşturma, exact-replace ve doğal dil akıllı düzenleme destekleniyor.\n"
            "Doğal düzenleme örneği:\n"
            "boru/config.py'deki model_name değerini llama3.2 yap\n\n"
            "Exact-replace örneği:\n"
            "dosya düzenle: boru/config.py\n"
            "Eski:\n"
            "model_name: str = \"llama3.1\"\n"
            "Yeni:\n"
            "model_name: str = \"llama3.2\""
            f"{project_guidance}"
        )

    @staticmethod
    def _pending_message() -> str:
        return (
            "Zaten onay bekleyen bir dosya değişikliği var. "
            "Önce 'onayla' veya 'iptal' demelisin."
        )

    @staticmethod
    def _normalize_command(
        value: str,
    ) -> str:
        text = " ".join(
            value.strip().split()
        )

        text = text.rstrip(
            ".!?"
        )

        return text.casefold()
