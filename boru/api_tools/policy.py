import ipaddress
import json
import re
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

from boru.api_tools.models import ApiMethod, ApiRequest


class SafeApiPolicy:
    _HOST_PATTERN = re.compile(
        r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
    )
    _SENSITIVE_KEY_PATTERN = re.compile(
        r"(?:password|passwd|parola|şifre|secret|api_?key|access_?token|private_?key)",
        re.IGNORECASE,
    )
    _SECRET_VALUE_PATTERNS = (
        re.compile(r"\bsk-(?:live-|proj-)?[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )

    def __init__(
        self,
        allowed_hosts: Sequence[str],
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
        max_body_characters: int = 16_384,
    ):
        hosts = tuple(host.strip().casefold().rstrip(".") for host in allowed_hosts)
        if max_body_characters < 1:
            raise ValueError("API gövde sınırı pozitif olmalıdır.")
        if len(hosts) > 64 or any(
            not host or len(host) > 253 or self._HOST_PATTERN.fullmatch(host) is None
            for host in hosts
        ):
            raise ValueError("API izin listesindeki host geçersiz.")
        self._allowed_hosts = frozenset(hosts)
        self._resolver = resolver
        self._max_body_characters = max_body_characters

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return tuple(sorted(self._allowed_hosts))

    def validate(self, request: ApiRequest) -> ApiRequest:
        parsed = self._parse_url(request.url)
        host = self._validate_endpoint(parsed)
        self._validate_public_addresses(host)
        return self._validate_body(request)

    @staticmethod
    def _parse_url(url: str):
        if len(url) > 2048 or any(
            ord(character) < 32 or ord(character) == 127 for character in url
        ):
            raise ValueError("API URL'si çok uzun veya güvenli olmayan karakter içeriyor.")
        return urlsplit(url)

    def _validate_endpoint(self, parsed) -> str:
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme.casefold() != "https":
            raise ValueError("Yalnızca HTTPS API adreslerine izin verilir.")
        if not host or parsed.username or parsed.password:
            raise ValueError("API adresinde geçerli ve kimlik bilgisiz bir host bulunmalıdır.")
        if parsed.port not in {None, 443}:
            raise ValueError("Yalnızca standart HTTPS portuna izin verilir.")
        if parsed.fragment:
            raise ValueError("API adresinde fragment kullanılamaz.")
        if host not in self._allowed_hosts:
            allowed = ", ".join(self.allowed_hosts) or "(izinli host yok)"
            raise ValueError(f"API host izin listesinde değil: {host}. İzinli: {allowed}")
        return host

    def _validate_public_addresses(self, host: str) -> None:
        try:
            records = self._resolver(host, 443, type=socket.SOCK_STREAM)
        except OSError as error:
            raise ValueError(f"API host çözümlenemedi: {host}") from error
        addresses = {record[4][0].split("%", 1)[0] for record in records}
        if not addresses:
            raise ValueError("API host herhangi bir IP adresine çözümlenmedi.")
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError("Özel, yerel veya ayrılmış ağ adreslerine erişim engellendi.")

    def _validate_body(self, request: ApiRequest) -> ApiRequest:
        if request.method not in {ApiMethod.POST, ApiMethod.PUT}:
            return request
        if not request.body or len(request.body) > self._max_body_characters:
            raise ValueError("API JSON gövdesi boş veya izin verilen sınırın üzerinde.")
        try:
            parsed_body = json.loads(request.body)
        except json.JSONDecodeError as error:
            raise ValueError("API gövdesi geçerli JSON olmalıdır.") from error
        if not isinstance(parsed_body, (dict, list)):
            raise ValueError("API gövdesi JSON nesnesi veya listesi olmalıdır.")
        if self._contains_sensitive_data(parsed_body):
            raise ValueError(
                "API gövdesinde parola, token veya erişim anahtarı benzeri hassas veri kullanılamaz."
            )
        canonical_body = json.dumps(parsed_body, ensure_ascii=False, separators=(",", ":"))
        return ApiRequest(request.method, request.url, canonical_body)

    @classmethod
    def _contains_sensitive_data(cls, value) -> bool:
        if isinstance(value, dict):
            return any(
                cls._SENSITIVE_KEY_PATTERN.search(str(key)) is not None
                or cls._contains_sensitive_data(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(cls._contains_sensitive_data(item) for item in value)
        if isinstance(value, str):
            return any(pattern.search(value) for pattern in cls._SECRET_VALUE_PATTERNS)
        return False
