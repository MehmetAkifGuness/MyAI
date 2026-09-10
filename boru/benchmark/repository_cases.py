from boru.benchmark.cases import CodingCase


def repository_catalog():
    """Offline multi-module fixtures, not a claim to external real-repo coverage."""
    return (
        CodingCase('repo_alias', 'repository',
            'Komut yönlendirmesinde benchmark durum ve benchmark durumu aynı yanıtı vermeli. '
            'Büyük/küçük harf ve çevre boşlukları desteklenmeli; bilinmeyen komutta None korunmalı.',
            (('subject.py', 'from app.commands import resolve\n'), ('app/__init__.py', ''),
             ('app/commands.py', 'from app.normalize import normalize\n\ndef resolve(text):\n'
              '    if normalize(text) == "benchmark durumu":\n        return "ready"\n    return None\n'),
             ('app/normalize.py', 'def normalize(text):\n    return text.strip().casefold()\n')),
            ('self.assertEqual(subject.resolve("benchmark durum"), "ready")',
             'self.assertEqual(subject.resolve(" BENCHMARK DURUMU "), "ready")',
             'self.assertIsNone(subject.resolve("sil"))')),
        CodingCase('repo_cache', 'repository',
            'read_config dönüşü çağıran tarafından değiştirildiğinde önbellek bozulmamalı. İç içe listeler de bağımsız olmalı.',
            (('subject.py', 'from app.config import read_config\n'), ('app/__init__.py', ''),
             ('app/config.py', 'from app.storage import CONFIG\n\ndef read_config():\n    return CONFIG.copy()\n'),
             ('app/storage.py', 'CONFIG = {"features": ["read"], "limit": 4}\n')),
            ('first = subject.read_config(); first["features"].append("write")',
             'self.assertEqual(subject.read_config()["features"], ["read"])',
             'self.assertEqual(subject.read_config()["limit"], 4)')),
        CodingCase('repo_pagination', 'repository',
            'list_page 1 tabanlı sayfalama yapmalı, boş listeyi desteklemeli. page<1 veya size<1 ValueError olmalı.',
            (('subject.py', 'from app.service import list_page\n'), ('app/__init__.py', ''),
             ('app/service.py', 'from app.paging import bounds\n\ndef list_page(items, page, size):\n'
              '    start, end = bounds(page, size)\n    return items[start:end]\n'),
             ('app/paging.py', 'def bounds(page, size):\n    return page * size, (page + 1) * size\n')),
            ('self.assertEqual(subject.list_page([1, 2, 3], 1, 2), [1, 2])',
             'self.assertEqual(subject.list_page([1, 2, 3], 2, 2), [3])',
             'self.assertEqual(subject.list_page([], 1, 2), [])',
             'self.assertRaises(ValueError, subject.list_page, [], 0, 2)',
             'self.assertRaises(ValueError, subject.list_page, [], 1, 0)')),
        CodingCase('repo_stock', 'repository',
            'reserve mevcut stoktan miktarı düşürmeli; miktar<=0 ve yetersiz stok ValueError olmalı. '
            'Başarısız istekte stok değişmemeli.',
            (('subject.py', 'from app.inventory import Inventory\n'), ('app/__init__.py', ''),
             ('app/inventory.py', 'from app.rules import validate\n\nclass Inventory:\n'
              '    def __init__(self, count):\n        self.count = count\n'
              '    def reserve(self, quantity):\n        self.count -= quantity\n'
              '        validate(self.count, quantity)\n        return self.count\n'),
             ('app/rules.py', 'def validate(stock, quantity):\n'
              '    if quantity <= 0 or stock < quantity:\n        raise ValueError("invalid")\n')),
            ('item = subject.Inventory(5)', 'self.assertEqual(item.reserve(3), 2)',
             'self.assertRaises(ValueError, item.reserve, 3)', 'self.assertEqual(item.count, 2)',
             'self.assertRaises(ValueError, item.reserve, -1)', 'self.assertEqual(item.count, 2)')),
        CodingCase('repo_settings', 'repository',
            'parse_config metinsel debug true/false değerlerini harf büyüklüğünden bağımsız ayrıştırmalı; '
            'bilinmeyen değer ValueError. timeout verilmezse 30, verilirse pozitif int olmalı.',
            (('subject.py', 'from app.settings import parse_config\n'), ('app/__init__.py', ''),
             ('app/settings.py', 'from app.parse import boolean\n\ndef parse_config(data):\n'
              '    return {"debug": boolean(data.get("debug", "false")), "timeout": int(data.get("timeout", 30))}\n'),
             ('app/parse.py', 'def boolean(text):\n    return bool(text)\n')),
            ('self.assertEqual(subject.parse_config({}), {"debug": False, "timeout": 30})',
             'self.assertTrue(subject.parse_config({"debug": "TRUE"})["debug"])',
             'self.assertRaises(ValueError, subject.parse_config, {"debug": "maybe"})',
             'self.assertRaises(ValueError, subject.parse_config, {"timeout": 0})')),
    )
