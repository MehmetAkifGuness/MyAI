from threading import RLock

from boru.tools.contracts import (
    ToolExecutorPort,
)
from boru.tools.edit_contracts import (
    EditProposalPreparer,
    EditRequestParser,
)
from boru.tools.edit_models import (
    EditProposal,
)
from boru.tools.models import (
    ToolCall,
)
from boru.tools.write_contracts import (
    WriteIntentDetector,
    WriteRequestParser,
)
from boru.tools.write_models import (
    WriteRequest,
)


class ControlledWriteCoordinator:
    """Create/edit isteklerini önizler ve yalnızca açık onaydan sonra uygular."""

    _APPROVE_COMMANDS = {
        "onayla",
        "yazmayı onayla",
        "dosya yazımını onayla",
        "değişikliği onayla",
        "düzenlemeyi onayla",
    }

    _CANCEL_COMMANDS = {
        "iptal",
        "vazgeç",
        "yazmayı iptal et",
        "değişikliği iptal et",
        "düzenlemeyi iptal et",
    }

    def __init__(
        self,
        *,
        parser: WriteRequestParser,
        intent_detector: WriteIntentDetector,
        executor: ToolExecutorPort,
        edit_parser: EditRequestParser | None = None,
        edit_preparer: EditProposalPreparer | None = None,
        preview_characters: int = 3000,
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

        self._parser = parser
        self._intent_detector = intent_detector
        self._executor = executor
        self._edit_parser = edit_parser
        self._edit_preparer = edit_preparer
        self._preview_characters = preview_characters
        self._pending: WriteRequest | EditProposal | None = None
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

            edit_response = self._try_stage_edit(
                user_message
            )

            if edit_response is not None:
                return edit_response

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

    def _execute_pending(
        self,
        pending: WriteRequest | EditProposal,
    ) -> str:
        if isinstance(
            pending,
            WriteRequest,
        ):
            return self._execute_create(
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