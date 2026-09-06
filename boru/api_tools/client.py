from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from boru.api_tools.models import ApiRequest, ApiResponse


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class BoundedHttpApiClient:
    def __init__(
        self,
        timeout_seconds: float = 15.0,
        max_response_bytes: int = 256 * 1024,
        opener=None,
    ):
        if timeout_seconds <= 0 or max_response_bytes < 1:
            raise ValueError("HTTP istemci sınırları pozitif olmalıdır.")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._opener = opener or build_opener(_NoRedirectHandler())

    def execute(self, request: ApiRequest) -> ApiResponse:
        data = request.body.encode("utf-8") if request.body else None
        http_request = Request(
            request.url,
            data=data,
            method=request.method.value,
            headers={
                "Accept": "application/json, text/plain;q=0.9",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "Boru/0.26",
            },
        )
        response = self._open(http_request)
        return self._read_response(response)

    def _open(self, http_request):
        try:
            return self._opener.open(http_request, timeout=self._timeout_seconds)
        except HTTPError as error:
            return error
        except (URLError, OSError, TimeoutError) as error:
            raise RuntimeError(f"HTTP API isteği tamamlanamadı: {error}") from error

    def _read_response(self, response) -> ApiResponse:
        with response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.code
            if 300 <= int(status) < 400:
                raise RuntimeError("HTTP yönlendirmeleri güvenlik politikası gereği engellendi.")
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "text/plain"} and not content_type.endswith("+json"):
                raise RuntimeError(f"Desteklenmeyen API içerik türü: {content_type}")
            data = response.read(self._max_response_bytes + 1)
            truncated = len(data) > self._max_response_bytes
            if truncated:
                data = data[: self._max_response_bytes]
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                body = data.decode(charset, errors="strict")
            except (LookupError, UnicodeDecodeError) as error:
                raise RuntimeError("API yanıtı güvenli metin olarak çözümlenemedi.") from error
            return ApiResponse(int(status), content_type, body, truncated)
