import os
import re
from urllib.parse import urlsplit

from boru.nlu.fuzzy_matcher import match_command_prefix
from boru.web.answer import GroundedWebAnswer, safe_label
from boru.web.content import document
from boru.web.http import SafeWebClient, check_public_input
from boru.web.search import WebSearch, SearchHit


class WebResearchCoordinator:
    _COMMAND = re.compile(r'^\s*(web ara|web oku|web araştır|internetten araştır|araştır)\s*:\s*(.*)$', re.I | re.S)
    _NATURAL = re.compile(r'^\s*(?:(?:internetten|webden|web üzerinde)\s+(.+?)\s+(?:araştır|araştırır mısın|araştır ve açıkla)|(?:lütfen\s+)?(.+?)\s+(?:konusunu\s+araştır|hakkında\s+araştırma\s+yap))[?.!]*\s*$', re.I)
    _TRIGGERS = ('web ara', 'web oku', 'web araştır', 'internetten araştır', 'araştır')
    HELP = ("WEB YARDIM\n'web ara: konu'; 'web oku: https://adres | soru'; "
            "'web araştır: soru'; 'internetten araştır: soru'; 'web durum'.\n"
            'Arama ve okuma salt-okunurdur. Sorgu arama sağlayıcısına gönderilir; yalnızca yazdığınız sorgu paylaşılır.')

    def __init__(self, model, *, client=None, search=None):
        self.client = client or SafeWebClient()
        self.search = search or WebSearch(self.client, os.getenv('BORU_WEB_SEARCH_KEY', '').strip())
        self.answers = GroundedWebAnswer(model)

    @property
    def has_pending(self):
        return False

    def resolve(self, message):
        folded = ' '.join(message.casefold().split())
        if folded in {'web yardım', 'web durum'}:
            return self.HELP + f'\nArama sağlayıcısı: {self.search.provider}\nSınırlar: 5 sonuç, 3 okunan sayfa, sayfa başına 1 MB; yalnızca herkese açık HTTPS.'
        match = self._COMMAND.match(message)
        natural = self._NATURAL.match(message) if match is None else None
        if match is None and natural is None:
            fuzzy = match_command_prefix(message, self._TRIGGERS)
            if fuzzy is not None:
                command, value = fuzzy
            elif folded.startswith(('web ', 'internetten araştır')):
                return self.HELP
            else:
                return None
        else:
            if match:
                command, value = match.group(1).casefold(), match.group(2).strip()
            else:
                command = 'web araştır'
                value = (natural.group(1) or natural.group(2)).strip()
            if command == 'araştır':
                command = 'web araştır'
        try:
            check_public_input(value)
            if command == 'web oku':
                url, _, question = value.partition('|')
                page = document(self.client.get(url.strip()))
                return self.answers.answer(question.strip() or 'Sayfanın ana bilgilerini Türkçe özetle.', [page])
            hits = self.search.search(value)
            direct_scope = False
            if not hits and command != 'web ara':
                scope = WebSearch.scoped_url(value)
                if scope and urlsplit(scope).path not in ('', '/'):
                    hits = [SearchHit('Kullanıcının belirttiği kaynak', scope)]
                    direct_scope = True
            if not hits:
                return 'WEB ARAMA\nSonuç alınamadı. Sorguyu daraltın veya doğrudan web oku kullanın.'
            if command == 'web ara':
                return 'WEB ARAMA\nBunlar arama bağlantılarıdır; sayfa içerikleri henüz okunmadı.\n' + '\n'.join(
                    f'- [{safe_label(hit.title)}]({hit.url})' for hit in hits)
            pages, errors, hosts, seen = [], 0, {}, set()
            for hit in hits:
                host = urlsplit(hit.url).hostname
                if hosts.get(host, 0) >= 2:
                    continue
                try:
                    page = document(self.client.get(hit.url))
                except (OSError, RuntimeError, ValueError):
                    errors += 1
                    continue
                if not WebSearch._relevant(value, SearchHit(page.title, page.url, page.text)):
                    errors += 1
                    continue
                if page.url in seen:
                    continue
                seen.add(page.url)
                pages.append(page)
                hosts[host] = hosts.get(host, 0) + 1
                if len(pages) == 3:
                    break
            if not pages:
                return 'WEB ARAŞTIRMA\nArama sonuçları bulundu, ancak sayfa içerikleri okunamadı. Kaynaklı yanıt üretilemedi.'
            question = re.sub(r'\bsite:[^\s]+', '', value, flags=re.I).strip()
            result = self.answers.answer(question, pages)
            if direct_scope:
                result += '\nNot: İlgili arama sonucu bulunamadı; site: ile belirttiğiniz adres doğrudan okundu.'
            if errors:
                result += f'\nNot: {errors} sayfa okunamadı; yanıt yalnızca listelenen kaynaklara dayanır.'
            return result
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            return 'WEB ARAŞTIRMA\nDurum: TAMAMLANAMADI\n' + str(error)
