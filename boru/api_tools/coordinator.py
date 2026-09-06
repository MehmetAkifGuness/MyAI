from dataclasses import dataclass

from boru.api_tools.models import ApiMethod, ApiRequest, ApiResponse


@dataclass(frozen=True, slots=True)
class PendingApiOperation:
    request: ApiRequest


class ControlledApiCoordinator:
    _CONFIRMATION = "api isteğini onayla"

    def __init__(self, parser, policy, client):
        self._parser = parser
        self._policy = policy
        self._client = client
        self._pending: PendingApiOperation | None = None

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    def resolve(self, user_message: str) -> str | None:
        if self._pending is not None:
            return self._resolve_pending(user_message)
        try:
            request = self._parser.parse(user_message)
            if request is None:
                return self._usage() if self._parser.is_api_intent(user_message) else None
            validated = self._policy.validate(request)
        except ValueError as error:
            return f"API isteği reddedildi: {error}"

        if validated.method is ApiMethod.GET:
            return self._execute(validated)
        self._pending = PendingApiOperation(validated)
        body_preview = f"\nJSON: {validated.body[:500]}" if validated.body else ""
        return (
            "API yazma isteği hazırlandı ancak gönderilmedi.\n"
            f"Metot: {validated.method.value}\nURL: {validated.url}{body_preview}\n"
            f"Göndermek için yalnızca '{self._CONFIRMATION}', vazgeçmek için 'iptal' yazın."
        )

    def _resolve_pending(self, user_message: str) -> str:
        normalized = " ".join(user_message.casefold().split())
        if normalized in {"iptal", "vazgeç"}:
            self._pending = None
            return "API isteği iptal edildi."
        if normalized != self._CONFIRMATION:
            return (
                "Onay bekleyen bir API isteği var. Göndermek için yalnızca "
                f"'{self._CONFIRMATION}', vazgeçmek için 'iptal' yazın."
            )
        pending = self._pending
        self._pending = None
        return self._execute(pending.request)

    def _execute(self, request: ApiRequest) -> str:
        try:
            validated = self._policy.validate(request)
            response = self._client.execute(validated)
        except ValueError as error:
            return f"API isteği yeniden doğrulanırken reddedildi: {error}"
        except RuntimeError as error:
            return f"API isteği başarısız: {error}"
        return self._format_response(validated, response)

    @staticmethod
    def _format_response(request: ApiRequest, response: ApiResponse) -> str:
        suffix = "\nNot: Yanıt çıktı sınırında kesildi." if response.truncated else ""
        return (
            "API YANITI\n"
            f"İstek: {request.method.value} {request.url}\n"
            f"HTTP durum: {response.status_code}\n"
            f"İçerik türü: {response.content_type}\n"
            f"Gövde:\n{response.body.strip() or '(boş)'}{suffix}"
        )

    @staticmethod
    def _usage() -> str:
        return (
            "Desteklenen biçimler: 'api get: HTTPS_URL', "
            "'api post: HTTPS_URL | JSON', 'api put: HTTPS_URL | JSON' ve "
            "'api delete: HTTPS_URL'."
        )
