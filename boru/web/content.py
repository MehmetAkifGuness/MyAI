import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title = [], []
        self._stack = []
        self._blocked = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (tag in {'script', 'style', 'noscript', 'svg', 'nav', 'footer', 'form', 'iframe'}
                  or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
                  or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style', ''), re.I)))
        if tag not in {'meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'}:
            if len(self._stack) >= 256:
                raise ValueError('HTML iç içe öğe sınırı aşıldı.')
            self._stack.append((tag, hidden))
            self._blocked += hidden
        if tag == 'title':
            self._in_title = True
        if not self._blocked and tag in {'p', 'div', 'article', 'section', 'li', 'h1', 'h2', 'h3', 'pre', 'br', 'tr'}:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                self._blocked -= sum(hidden for _, hidden in self._stack[index:])
                del self._stack[index:]
                break
        if tag == 'title':
            self._in_title = False
        if not self._blocked and tag in {'p', 'div', 'li', 'h1', 'h2', 'h3', 'pre', 'tr'}:
            self.parts.append('\n')

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        elif not self._blocked:
            self.parts.append(data)


@dataclass(frozen=True)
class WebDocument:
    url: str
    title: str
    text: str
    fetched_at: str


def document(response):
    title = response.url
    if response.content_type in ('text/html', 'application/xhtml+xml'):
        parser = PageText()
        parser.feed(response.text)
        title = ' '.join(''.join(parser.title).split())[:180] or title
        text = ''.join(parser.parts)
    else:
        text = response.text
    lines = [' '.join(line.split()) for line in text.splitlines() if line.strip()]
    text = '\n'.join(lines)[:60000]
    if len(text) < 40:
        raise ValueError('Sayfada yeterli okunabilir metin yok (JavaScript veya erişim engeli olabilir).')
    return WebDocument(response.url, title, text, datetime.now(timezone.utc).isoformat(timespec='seconds'))


def passages(text, question, limit=2400):
    words = set(re.findall(r'\w{3,}', question.casefold()))
    for turkish, english in {'hata': ('error', 'exception'), 'geçersiz': ('invalid',),
                             'güvenlik': ('security',), 'kurulum': ('installation',)}.items():
        if turkish in words:
            words.update(english)
    chunks = [line[i:i + 700] for line in text.splitlines() for i in range(0, len(line), 700)]
    def relevance(item):
        score = len(words & set(re.findall(r'\w{3,}', item[1].casefold())))
        # A function signature's surrounding prose is more useful than scattered REPL examples.
        return (-(score * (0.25 if item[1].startswith('>>>') else 1)), item[0])
    ranked = sorted(enumerate(chunks), key=relevance)
    chosen, used = {}, 0
    for index, chunk in ranked:
        if index in chosen:
            continue
        window = [(i, chunks[i]) for i in range(max(0, index - 1), min(len(chunks), index + 3)) if i not in chosen]
        size = sum(len(line) + 1 for _, line in window)
        if used + size <= limit:
            chosen.update(window)
            used += size
    return '\n'.join(chunk for _, chunk in sorted(chosen.items()))
