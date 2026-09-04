from threading import RLock

from boru.tools.contracts import (
    ToolExecutorPort,
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
    """Yazma isteğini önce beklemeye alır, yalnızca açık onaydan sonra çalıştırır."""

    _APPROVE_COMMANDS = {
        "onayla",
        "yazmayı onayla",
        "dosya yazımını onayla",
        "değişikliği onayla",
    }

    _CANCEL_COMMANDS = {
        "iptal",
        "vazgeç",
        "yazmayı iptal et",
        "değişikliği iptal et",
    }

    def __init__(
        self,
        *,
        parser: WriteRequestParser,
        intent_detector: WriteIntentDetector,
        executor: ToolExecutorPort,
        preview_characters: int = 3000,
    ):
        if preview_characters < 1:
            raise ValueError(
                "preview_characters en az 1 olmalıdır."
            )

        self._parser = parser
        self._intent_detector = (
            intent_detector
        )
        self._executor = executor
        self._preview_characters = (
            preview_characters
        )

        self._pending: WriteRequest | None = (
            None
        )

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
                and normalized
                in self._APPROVE_COMMANDS
            ):
                pending = self._pending
                self._pending = None

                return self._execute(
                    pending
                )

            if (
                self._pending is not None
                and normalized
                in self._CANCEL_COMMANDS
            ):
                self._pending = None

                return (
                    "Bekleyen dosya yazma işlemi iptal edildi."
                )

            request = self._parser.parse(
                user_message
            )

            if request is not None:
                if self._pending is not None:
                    return (
                        "Zaten onay bekleyen bir dosya yazma işlemi var. "
                        "Önce 'onayla' veya 'iptal' demelisin."
                    )

                self._pending = request

                return self._render_preview(
                    request
                )

            if self._intent_detector.is_write_intent(
                user_message
            ):
                if self._pending is not None:
                    return (
                        "Zaten onay bekleyen bir dosya yazma işlemi var. "
                        "Önce 'onayla' veya 'iptal' demelisin."
                    )

                return (
                    "Bu sürüm kontrollü olarak yalnızca tam içerik verilen "
                    "yeni dosya oluşturma işlemini destekliyor. "
                    "Örnek biçim:\n"
                    "dosya oluştur: notes/ornek.txt\n"
                    "İçerik:\n"
                    "Merhaba Börü"
                )

        return None

    def _execute(
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

    def _render_preview(
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