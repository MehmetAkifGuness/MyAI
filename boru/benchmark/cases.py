from dataclasses import dataclass


@dataclass(frozen=True)
class CodingCase:
    identifier: str
    category: str
    prompt: str
    sources: tuple[tuple[str, str], ...]
    checks: tuple[str, ...]
    action: str = "edit"


def catalog():
    specs = (
        ("addition", "add negatif sayılar dahil toplama yapmalı.", "def add(a, b):\n    return a - b\n",
         ("self.assertEqual(subject.add(2, 3), 5)", "self.assertEqual(subject.add(-3, 1), -2)")),
        ("mean", "mean boş listede None, diğerlerinde aritmetik ortalama döndürmeli.", "def mean(xs):\n    return sum(xs)\n",
         ("self.assertIsNone(subject.mean([]))", "self.assertEqual(subject.mean([2, 6]), 4)")),
        ("dedupe", "unique tekrarları kaldırmalı, ilk görülme sırasını korumalı.", "def unique(xs):\n    return xs\n",
         ("self.assertEqual(subject.unique([3, 1, 3, 2]), [3, 1, 2])", "self.assertEqual(subject.unique([]), [])")),
        ("clamp", "clamp sayıyı alt ve üst sınır arasında tutmalı.", "def clamp(x, low, high):\n    return x\n",
         ("self.assertEqual(subject.clamp(-1, 0, 10), 0)", "self.assertEqual(subject.clamp(12, 0, 10), 10)", "self.assertEqual(subject.clamp(5, 0, 10), 5)")),
        ("median", "median boş listede None, çift uzunlukta orta iki değerin ortalamasını döndürmeli.", "def median(xs):\n    return xs[0]\n",
         ("self.assertIsNone(subject.median([]))", "self.assertEqual(subject.median([9, 1, 4, 2]), 3)")),
        ("slug", "slug çevre boşluklarını silmeli, küçük harfe çevirmeli ve boşluk gruplarını tire yapmalı.", "def slug(text):\n    return text\n",
         ("self.assertEqual(subject.slug('  Hello   WORLD '), 'hello-world')", "self.assertEqual(subject.slug(''), '')")),
        ("counts", "counts her elemanın tekrar sayısını sözlük olarak döndürmeli.", "def counts(xs):\n    return dict.fromkeys(xs, 1)\n",
         ("self.assertEqual(subject.counts(['a', 'b', 'a']), {'a': 2, 'b': 1})", "self.assertEqual(subject.counts([]), {})")),
        ("chunks", "chunks n boyutunda alt listeler üretmeli; n<=0 ValueError olmalı.", "def chunks(xs, n):\n    return [xs]\n",
         ("self.assertEqual(subject.chunks([1, 2, 3], 2), [[1, 2], [3]])", "self.assertRaises(ValueError, subject.chunks, [1], 0)")),
        ("leap", "is_leap Gregoryen artık yıl kuralını uygulamalı.", "def is_leap(year):\n    return year % 4 == 0\n",
         ("self.assertFalse(subject.is_leap(1900))", "self.assertTrue(subject.is_leap(2000))", "self.assertTrue(subject.is_leap(2024))")),
        ("factorial", "factorial sıfırda 1 döndürmeli; negatif girdiyi ValueError ile reddetmeli.", "def factorial(n):\n    return n\n",
         ("self.assertEqual(subject.factorial(0), 1)", "self.assertEqual(subject.factorial(5), 120)", "self.assertRaises(ValueError, subject.factorial, -1)")),
        ("binary_search", "find sıralı listede elemanın indeksini, yoksa -1 döndürmeli.", "def find(xs, target):\n    return 0\n",
         ("self.assertEqual(subject.find([1, 4, 8], 8), 2)", "self.assertEqual(subject.find([], 3), -1)", "self.assertEqual(subject.find([1, 4], 2), -1)")),
        ("flatten", "flatten bir seviyelik listeleri düzleştirmeli.", "def flatten(xs):\n    return xs\n",
         ("self.assertEqual(subject.flatten([[1, 2], [], [3]]), [1, 2, 3])",)),
        ("merge", "merge iki sözlüğü yeni sözlükte birleştirmeli; sağ taraf öncelikli, girdiler değişmemeli.", "def merge(a, b):\n    a.update(b)\n    return a\n",
         ("a = {'x': 1}; result = subject.merge(a, {'x': 2, 'y': 3}); self.assertEqual(a, {'x': 1}); self.assertEqual(result, {'x': 2, 'y': 3})",)),
        ("parse_bool", "parse_bool true/false metnini büyük-küçük harf ve çevre boşluklarından bağımsız ayrıştırmalı; diğer metinler ValueError.", "def parse_bool(text):\n    return bool(text)\n",
         ("self.assertFalse(subject.parse_bool(' FALSE '))", "self.assertTrue(subject.parse_bool('true'))", "self.assertRaises(ValueError, subject.parse_bool, 'maybe')")),
        ("mutable_default", "append_item list parametresi verilmezse her çağrıda yeni liste kullanmalı.", "def append_item(item, items=[]):\n    items.append(item)\n    return items\n",
         ("self.assertEqual(subject.append_item(1), [1]); self.assertEqual(subject.append_item(2), [2])",)),
        ("new_palindrome", "is_palindrome(text) ekle: harf/rakam dışındakileri ve harf büyüklüğünü yok say.", "# Implement the requested function.\n",
         ("self.assertTrue(subject.is_palindrome('A man, a plan, a canal: Panama'))", "self.assertFalse(subject.is_palindrome('python'))")),
        ("new_pairs", "pairs(xs) komşu ikilileri tuple listesi olarak döndürmeli.", "# Implement the requested function.\n",
         ("self.assertEqual(subject.pairs([1, 2, 3]), [(1, 2), (2, 3)])", "self.assertEqual(subject.pairs([]), [])")),
        ("new_partition", "partition(xs, predicate) doğru ve yanlış elemanları sıralarını koruyan iki liste olarak döndürmeli.", "# Implement the requested function.\n",
         ("self.assertEqual(subject.partition([1, 2, 3, 4], lambda n: n % 2 == 0), ([2, 4], [1, 3]))",)),
        ("new_get_path", "get_path(data, keys, default=None) iç içe sözlüklerden değer okumalı; eksik yolda default döndürmeli.", "# Implement the requested function.\n",
         ("self.assertEqual(subject.get_path({'a': {'b': 3}}, ['a', 'b']), 3)", "self.assertEqual(subject.get_path({}, ['a'], 7), 7)")),
        ("new_invert", "invert(mapping) aynı değeri paylaşan anahtarları liste halinde gruplayan ters sözlük oluşturmalı.", "# Implement the requested function.\n",
         ("self.assertEqual(subject.invert({'a': 1, 'b': 1, 'c': 2}), {1: ['a', 'b'], 2: ['c']})",)),
    )
    result = [CodingCase(name, "new_function" if name.startswith("new_") else "bugfix", prompt,
                         (("subject.py", source),), checks) for name, prompt, source, checks in specs]
    for name, prompt, source, expression, checks in (
        ("pricing", "Yüzde indirimi doğru uygula; total fiyat ile adedi çarpmalı.", "def discount(price, percent):\n    return price - percent\n", "discount(price, percent) * quantity", ("self.assertEqual(subject.total(200, 3, 10), 540)",)),
        ("stock", "available stok sıfır olduğunda False olmalı; label buna göre sold/ready döndürmeli.", "def available(stock):\n    return stock >= 0\n", "'ready' if available(stock) else 'sold'", ("self.assertEqual(subject.label(0), 'sold')", "self.assertEqual(subject.label(1), 'ready')")),
        ("normalize", "normalize çevre boşluklarını silip küçük harfe çevirmeli; same bunu kullanmalı.", "def normalize(text):\n    return text.lower()\n", "normalize(a) == normalize(b)", ("self.assertTrue(subject.same(' A ', 'a'))",)),
        ("pagination", "offset 1 tabanlı sayfa için başlangıcı hesaplamalı; page liste dilimini döndürmeli.", "def offset(number, size):\n    return number * size\n", "xs[offset(number, size):offset(number, size) + size]", ("self.assertEqual(subject.page([1, 2, 3, 4], 1, 2), [1, 2])",)),
        ("tax", "tax yüzde oranını kullanmalı; gross net tutara vergiyi eklemeli.", "def tax(net, rate):\n    return net * rate\n", "net + tax(net, rate)", ("self.assertEqual(subject.gross(100, 20), 120)",)),
    ):
        function, signature = {"pricing": ("total", "price, quantity, percent"), "stock": ("label", "stock"),
                               "normalize": ("same", "a, b"), "pagination": ("page", "xs, number, size"),
                               "tax": ("gross", "net, rate")}[name]
        helper = source.split("(")[0].removeprefix("def ")
        caller = f"from helper import {helper}\n\ndef {function}({signature}):\n    return {expression}\n"
        result.append(CodingCase(name, "related_files", prompt, (("helper.py", source), ("subject.py", caller)), checks))
    for name, prompt in (
        ("currency", "convert_currency(amount) ekle; hangi para birimleri ve hangi kur kullanılacağı belirtilmedi. Önce açıklama iste."),
        ("sort_policy", "Kayıtları sırala; sıralama alanı ve yönü verilmedi. Önce açıklama iste."),
        ("auth_policy", "Kullanıcı erişimini sınırla; roller ve izinler verilmedi. Önce açıklama iste."),
        ("rounding", "Fiyatı yuvarla; hassasiyet ve yuvarlama kuralı verilmedi. Önce açıklama iste."),
        ("test_conflict", "VALUE=3 istiyorum fakat mevcut sözleşme VALUE=2 gerektiriyor. Çelişkiyi çözmek için açıklama iste."),
    ):
        result.append(CodingCase(name, "clarification", prompt, (("subject.py", "VALUE = 2\n"),), (), "clarify"))
    return tuple(result)
