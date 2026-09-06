import re

from boru.api_tools.models import ApiMethod, ApiRequest


class RuleBasedApiRequestParser:
    _PATTERN = re.compile(
        r"^api\s+(get|post|put|delete)\s*:\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    def parse(self, user_message: str) -> ApiRequest | None:
        match = self._PATTERN.fullmatch(user_message.strip())
        if not match:
            return None

        method = ApiMethod(match.group(1).upper())
        payload = match.group(2).strip()
        if not payload:
            raise ValueError("API URL'si boş olamaz.")

        url, separator, body = payload.partition("|")
        if method in {ApiMethod.POST, ApiMethod.PUT} and not separator:
            raise ValueError(
                "POST ve PUT için 'URL | JSON gövdesi' biçimini kullanın."
            )
        if method in {ApiMethod.GET, ApiMethod.DELETE} and separator:
            raise ValueError("GET ve DELETE isteklerinde gövdeye izin verilmez.")

        return ApiRequest(method, url.strip(), body.strip())

    @staticmethod
    def is_api_intent(user_message: str) -> bool:
        return re.match(r"^\s*api\s+", user_message, re.IGNORECASE) is not None
