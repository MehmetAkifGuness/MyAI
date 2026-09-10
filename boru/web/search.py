import json
import re
from xml.etree import ElementTree
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from boru.web.http import check_public_input, normalize_url


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str = ''


class _DuckResults(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hits, self._title, self._href = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and set(attrs.get('class', '').split()) & {'result__a', 'result-link'}:
            self._href, self._title = attrs.get('href'), []

    def handle_data(self, value):
        if self._href:
            self._title.append(value)

    def handle_endtag(self, tag):
        if tag == 'a' and self._href:
            url = urljoin('https://html.duckduckgo.com', self._href)
            parsed = urlsplit(url)
            if parsed.hostname in {'duckduckgo.com', 'html.duckduckgo.com'}:
                url = parse_qs(parsed.query).get('uddg', [''])[0]
            try:
                self.hits.append(SearchHit(' '.join(''.join(self._title).split())[:180], normalize_url(url)))
            except ValueError:
                pass
            self._href = None


class WebSearch:
    def __init__(self, client, api_key=''):
        self.client, self._api_key = client, api_key
        self.last_provider = ''

    @property
    def provider(self):
        return 'Brave Search API' if self._api_key else 'DuckDuckGo HTML / Bing RSS yedeği'

    def search(self, query, limit=5):
        check_public_input(query)
        if not 1 <= limit <= 5:
            raise ValueError('Arama sonucu sınırı 1-5 olmalıdır.')
        if self._api_key:
            self.last_provider = 'Brave Search API'
            response = self.client.get('https://api.search.brave.com/res/v1/web/search?' +
                                       urlencode({'q': query, 'count': limit}), api_key=self._api_key)
            data = json.loads(response.text)
            hits = []
            for item in data.get('web', {}).get('results', [])[:10]:
                try:
                    hits.append(SearchHit(str(item.get('title', ''))[:180], normalize_url(item['url']),
                                          str(item.get('description', ''))[:1000]))
                except (ValueError, KeyError, TypeError):
                    continue
        else:
            try:
                self.last_provider = 'DuckDuckGo HTML'
                response = self.client.get('https://html.duckduckgo.com/html/?' + urlencode({'q': query}))
                if any(term in response.text.lower() for term in ('anomaly.js', 'challenge-form', 'bots use duckduckgo')):
                    raise RuntimeError('Arama sağlayıcısı CAPTCHA istiyor.')
                parser = _DuckResults()
                parser.feed(response.text)
                hits = [hit for hit in parser.hits if self._relevant(query, hit)]
            except (OSError, RuntimeError, ValueError):
                hits = []
            if not hits:
                hits = self._bing(query)
        unique = {}
        for hit in hits:
            if self._relevant(query, hit):
                unique.setdefault(hit.url, hit)
        return list(unique.values())[:limit]

    @staticmethod
    def scoped_url(query):
        match = re.search(r'\bsite:([^\s]+)', query, re.I)
        return normalize_url('https://' + match.group(1).rstrip('.,;')) if match else None

    @classmethod
    def _relevant(cls, query, hit):
        scope = cls.scoped_url(query)
        if scope:
            target, allowed = urlsplit(hit.url), urlsplit(scope)
            if not (target.hostname == allowed.hostname or target.hostname.endswith('.' + allowed.hostname)):
                return False
            return target.path.startswith(allowed.path)
        stop = {'nedir', 'nasıl', 'hangi', 'demek', 'için', 'göre', 'araştır', 'açıkla',
                'arasındaki', 'fark', 'ile', 'resmi', 'resmî', 'official', 'documentation'}
        terms = set(re.findall(r'\w{3,}', query.casefold())) - stop
        content = (hit.title + ' ' + hit.url + ' ' + hit.snippet).casefold()
        return bool(terms) and any(term in content for term in terms)

    def _bing(self, query):
        self.last_provider = 'Bing RSS'
        response = self.client.get('https://www.bing.com/search?' + urlencode({'q': query, 'format': 'rss'}))
        if '<!doctype' in response.text.lower() or '<!entity' in response.text.lower():
            raise ValueError('Arama sağlayıcısı geçerli RSS döndürmedi.')
        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            raise ValueError('Arama sağlayıcısının yanıtı okunamadı; web oku veya Brave Search kullanın.') from None
        if root.tag != 'rss':
            raise ValueError('Arama sağlayıcısının RSS biçimi değişmiş.')
        hits = []
        for item in root.findall('./channel/item')[:10]:
            try:
                hits.append(SearchHit((item.findtext('title') or '')[:180], normalize_url(item.findtext('link') or ''),
                                      (item.findtext('description') or '')[:1000]))
            except ValueError:
                continue
        return hits
