"""Read-only HTTPS transport: resolve, validate, then connect to that exact IP."""
import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass
from http.client import HTTPSConnection
from time import monotonic
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from boru.api_tools.policy import SafeApiPolicy


def check_public_input(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError('Web isteği 1-2048 karakter olmalıdır.')
    if any(ord(c) < 32 for c in value) or SafeApiPolicy._contains_sensitive_data(value):
        raise ValueError('Web isteği kontrol karakteri veya hassas veri içeriyor.')
    if re.search(r'(?i)(?:password|parola|şifre|secret|token|api[_-]?key)\s*[=:]', unquote(value)):
        raise ValueError('Hassas bilgi içeren sorgu internete gönderilmez.')


def normalize_url(url):
    check_public_input(url)
    parsed = urlsplit(url)
    if parsed.scheme.lower() != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Yalnızca kimlik bilgisi içermeyen HTTPS adresi okunabilir.')
    if parsed.port not in (None, 443) or '\\' in url:
        raise ValueError('Web adresinin portu veya biçimi desteklenmiyor.')
    host = parsed.hostname.encode('idna').decode('ascii').lower().rstrip('.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
            raise ValueError('Web alan adı geçersiz.') from None
        if '.' not in host or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError('Yerel ağ adresi okunamaz.')
    else:
        if not address.is_global or address.is_multicast:
            raise ValueError('Yerel/ayrılmış ağ adresi okunamaz.')
    netloc = '[' + host + ']' if ':' in host else host
    return urlunsplit(('https', netloc, quote(parsed.path or '/', safe='/%:@-._~!$&*+,;='),
                       quote(parsed.query, safe='=&%/:?@-._~!$*+,;'), ''))


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        raw = socket.create_connection((self._address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


@dataclass(frozen=True)
class WebResponse:
    url: str
    text: str
    content_type: str


class SafeWebClient:
    def __init__(self, *, resolver=socket.getaddrinfo, connection_factory=_PinnedHTTPSConnection,
                 timeout=20, max_bytes=1_000_000, clock=monotonic):
        self._resolver, self._connection_factory = resolver, connection_factory
        self.timeout, self.max_bytes, self._clock = timeout, max_bytes, clock

    def get(self, url, *, api_key=None):
        if api_key and (len(api_key) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in api_key)):
            raise ValueError('Arama anahtarı biçimi geçersiz.')
        url = normalize_url(url)
        deadline = self._clock() + self.timeout
        visited = set()
        for _ in range(4):
            if url in visited:
                raise ValueError('Web yönlendirme döngüsü engellendi.')
            visited.add(url)
            parsed = urlsplit(url)
            host = parsed.hostname
            if api_key and (host != 'api.search.brave.com' or parsed.path != '/res/v1/web/search'):
                raise ValueError('Arama anahtarı yalnızca arama sağlayıcısına gönderilebilir.')
            try:
                addresses = list(dict.fromkeys(record[4][0] for record in
                    self._resolver(host, 443, type=socket.SOCK_STREAM)))
                if not addresses or any(not ipaddress.ip_address(a).is_global or
                                        ipaddress.ip_address(a).is_multicast for a in addresses):
                    raise ValueError('Web hedefi özel veya ayrılmış ağa çözümleniyor.')
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError()
                connection = self._connection_factory(host, addresses[0], remaining)
                try:
                    headers = {'User-Agent': 'Boru/13.0 (read-only research)',
                               'Accept': 'text/html,text/plain,application/json', 'Accept-Encoding': 'identity'}
                    if api_key:
                        headers['X-Subscription-Token'] = api_key
                    target = parsed.path + ('?' + parsed.query if parsed.query else '')
                    connection.request('GET', target, headers=headers)
                    response = connection.getresponse()
                    if response.status in (301, 302, 303, 307, 308):
                        if api_key:
                            raise ValueError('Anahtarlı aramada yönlendirme engellendi.')
                        location = response.getheader('Location')
                        if not location:
                            raise ValueError('Web yönlendirme adresi eksik.')
                        url = normalize_url(urljoin(url, location))
                        continue
                    if response.status != 200:
                        raise ValueError(f'Web sunucusu HTTP {response.status} döndürdü.')
                    if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                        raise ValueError('Sıkıştırılmış web yanıtı desteklenmiyor.')
                    content_type = response.getheader('Content-Type', '').lower()
                    mime = content_type.split(';')[0].strip()
                    if mime not in ('text/html', 'application/xhtml+xml', 'text/plain', 'application/json',
                                    'text/xml', 'application/xml', 'application/rss+xml'):
                        raise ValueError('Yalnızca HTML/metin/JSON okunabilir; indirme yapılmadı.')
                    chunks, total = [], 0
                    while True:
                        remaining = deadline - self._clock()
                        if remaining <= 0:
                            raise TimeoutError()
                        if connection.sock is not None:
                            connection.sock.settimeout(remaining)
                        chunk = response.read(min(16384, self.max_bytes + 1 - total))
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise ValueError('Web sayfası 1 MB okuma sınırını aşıyor.')
                        chunks.append(chunk)
                    match = re.search(r'charset=["\']?([\w-]+)', content_type)
                    encoding = match.group(1) if match else 'utf-8'
                    try:
                        text = b''.join(chunks).decode(encoding, errors='replace')
                    except LookupError:
                        text = b''.join(chunks).decode('utf-8', errors='replace')
                    return WebResponse(url, text, mime)
                finally:
                    connection.close()
            except (OSError, TimeoutError) as error:
                raise RuntimeError('Web bağlantısı tamamlanamadı: ' + type(error).__name__) from None
        raise ValueError('Web yönlendirme sınırı aşıldı.')
