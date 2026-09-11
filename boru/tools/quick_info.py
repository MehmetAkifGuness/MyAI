from __future__ import annotations

import ast
import datetime
import json
import logging
import operator
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Kısa süreli bellek önbelleği (Önbellek süresi: 5 dakika)
_CACHE: Dict[str, Tuple[float, str]] = {}
CACHE_TTL_SECONDS = 300.0


def _get_cached(key: str) -> Optional[str]:
    entry = _CACHE.get(key)
    if entry:
        timestamp, value = entry
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return value
    return None


def _set_cached(key: str, value: str) -> None:
    _CACHE[key] = (time.time(), value)


def get_weather(location: str = "Istanbul") -> Tuple[bool, str]:
    """
    Belirtilen şehir için canlı hava durumu bilgisini çeker.
    wttr.in servisini Türkçe çıktıyla kullanır.
    """
    clean_loc = location.strip() or "Istanbul"
    cache_key = f"weather_{clean_loc.lower()}"
    cached = _get_cached(cache_key)
    if cached:
        return True, cached

    try:
        ascii_loc = clean_loc.lower().translate(str.maketrans("ğüşıöç", "gusioc"))
        encoded_loc = urllib.parse.quote_plus(ascii_loc)
        url = f"https://wttr.in/{encoded_loc}?format=%C+%t&lang=tr"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "curl/7.68.0", "Accept-Language": "tr-TR,tr;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
            if text and not text.startswith("<html") and len(text) < 100:
                result = f"{clean_loc.capitalize()} için hava durumu: {text}."
                _set_cached(cache_key, result)
                return True, result

        return False, f"{clean_loc.capitalize()} için hava durumu bilgisi alınamadı."
    except Exception as e:
        logger.debug(f"wttr.in hava durumu çekme hatası: {e}")

    # Fallback: Canlı web arama motoru üzerinden çek (MGM / Google Weather)
    try:
        from boru.tools.web_search import search_web_live
        ok_w, search_text = search_web_live(f"{clean_loc} hava durumu", max_results=1)
        if ok_w and search_text:
            lines = [l.strip() for l in search_text.splitlines() if l.strip() and not l.startswith("🌐") and not l.startswith("1.")]
            if lines:
                res = f"{clean_loc.capitalize()} için güncel hava durumu: {lines[0][:140]}."
                _set_cached(cache_key, res)
                return True, res
    except Exception:
        pass

    return False, f"{clean_loc.capitalize()} için hava durumu servisine şu anda ulaşılamıyor."


CURRENCY_NAMES = {
    "USD": "Dolar",
    "EUR": "Euro",
    "GBP": "İngiliz Sterlini",
    "AZN": "Azerbaycan Manatı",
    "JPY": "Japon Yeni",
    "CHF": "İsviçre Frangı",
    "KWD": "Kuveyt Dinarı",
    "SAR": "Suudi Arabistan Riyali",
    "AED": "BAE Dirhemi",
    "RUB": "Rus Rublesi",
    "CNY": "Çin Yuanı",
    "CAD": "Kanada Doları",
    "AUD": "Avustralya Doları",
    "TRY": "Türk Lirası",
}


def get_currency_rate(base: str = "USD", target: str = "TRY") -> Tuple[bool, str]:
    """
    Güncel ve güvenilir döviz kurlarını anlık API üzerinden çeker.
    """
    base_code = base.upper().strip()
    target_code = target.upper().strip()
    cache_key = f"fx_{base_code}_{target_code}"
    cached = _get_cached(cache_key)
    if cached:
        return True, cached

    base_name = CURRENCY_NAMES.get(base_code, base_code)
    target_name = CURRENCY_NAMES.get(target_code, target_code)

    # 1. Öncelikli Güvenilir Servis: open.er-api.com (Ücretsiz, limitsiz ve güncel)
    try:
        url = f"https://open.er-api.com/v6/latest/{base_code}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            rates = data.get("rates", {})
            val = rates.get(target_code)
            if val is not None:
                result = f"1 {base_name} şu anda yaklaşık {val:.2f} {target_name} seviyesinde."
                _set_cached(cache_key, result)
                return True, result
    except Exception as e:
        logger.debug(f"Birincil döviz API hatası ({base_code}): {e}")

    # 2. Fallback: Frankfurter API
    try:
        url = f"https://api.frankfurter.app/latest?from={base_code}&to={target_code}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            rates = data.get("rates", {})
            val = rates.get(target_code)
            if val is not None:
                result = f"1 {base_name} şu anda yaklaşık {val:.2f} {target_name} seviyesinde."
                _set_cached(cache_key, result)
                return True, result
    except Exception as e:
        logger.debug(f"Fallback döviz API hatası: {e}")

    # 3. Fallback: Canlı web arama motoru
    try:
        from boru.tools.web_search import search_web_live
        ok_live, live_text = search_web_live(f"1 {base_name} kaç tl canlı döviz kuru", max_results=1)
        if ok_live and live_text:
            return True, f"{base_name} canlı kuru:\n{live_text}"
    except Exception:
        pass

    return False, f"{base_name} kuru servisine şu anda ulaşılamıyor."


# Türkiye'nin 81 ili ve popüler dünya şehirleri
KNOWN_CITIES = [
    "kahramanmaraş", "afyonkarahisar", "şanlıurfa", "diyarbakır",
    "adana", "adıyaman", "afyon", "ağrı", "aksaray", "amasya", "ankara",
    "antalya", "ardahan", "artvin", "aydın", "balıkesir", "bartın",
    "batman", "bayburt", "bilecik", "bingöl", "bitlis", "bolu", "burdur",
    "bursa", "çanakkale", "çankırı", "çorum", "denizli", "düzce",
    "edirne", "elazığ", "erzincan", "erzurum", "eskişehir", "gaziantep",
    "antep", "giresun", "gümüşhane", "hakkari", "hatay", "antakya", "ığdır",
    "isparta", "istanbul", "izmir", "maraş", "karabük", "karaman", "kars",
    "kastamonu", "kayseri", "kilis", "kırıkkale", "kırklareli", "kırşehir",
    "kocaeli", "izmit", "konya", "kütahya", "malatya", "manisa", "mardin",
    "mersin", "içel", "muğla", "muş", "nevşehir", "niğde", "ordu", "osmaniye",
    "rize", "sakarya", "adapazarı", "samsun", "urfa", "siirt", "sinop", "sivas",
    "şırnak", "tekirdağ", "tokat", "trabzon", "tunceli", "uşak", "van", "yalova",
    "yozgat", "zonguldak",
    "londra", "paris", "berlin", "roma", "madrid", "tokyo", "bakü", "new york", "moskova"
]
KNOWN_CITIES_SORTED = sorted(KNOWN_CITIES, key=len, reverse=True)


TURKISH_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
TURKISH_MONTHS = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
]


def get_current_time_and_date(mode: str = "both") -> str:
    """Sistem yerel saatini ve Türkçe tarihini döndürür."""
    now = datetime.datetime.now()
    day_name = TURKISH_DAYS[now.weekday()]
    month_name = TURKISH_MONTHS[now.month]
    time_str = now.strftime("%H:%M")
    date_str = f"{now.day} {month_name} {now.year}, {day_name}"

    if mode == "time":
        return f"Şu anda saat {time_str}."
    elif mode == "date":
        return (
            f"Bugün: {now.day} {month_name} {now.year}, {day_name} "
            f"(Gün: {now.day}, Ay: {month_name} [{now.month}. ay], Yıl: {now.year})."
        )
    elif mode == "day":
        return f"Bugün günlerden {day_name}."
    elif mode == "year":
        return f"Şu anda {now.year} yılındayız."
    elif mode == "month":
        return f"Şu anda {month_name} ayındayız."
    else:
        return f"Bugün {date_str}, saat {time_str}."


_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_ast_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp):
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        op_type = type(node.op)
        if op_type in _SAFE_OPERATORS:
            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise ZeroDivisionError("Sıfıra bölme hatası")
            if op_type == ast.Pow and (right > 1000 or left > 100000):
                raise ValueError("Hesaplanamayacak kadar büyük üs")
            return _SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_ast_node(node.operand)
        op_type = type(node.op)
        if op_type in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[op_type](operand)
    raise ValueError("Desteklenmeyen ifade")


def _turkish_percent_suffix(num_str: str) -> str:
    """Yüzde sayıları için doğru Türkçe iyelik eki üretir (%20'si, %18'i, %10'u vb.)"""
    last = num_str.strip()
    if last.endswith(("2", "5", "7", "8", "20", "50", "70", "80")):
        return "'si"
    elif last.endswith(("6", "40", "60", "90")):
        return "'sı"
    elif last.endswith(("3", "4", "100")):
        return "'ü"
    elif last.endswith(("9", "10", "30")):
        return "'u"
    return "'i"


def evaluate_math_expression(text: str) -> Optional[str]:
    """Türkçe veya sembolik matematiksel hesaplama sorularını güvenli çözer."""
    cleaned = text.lower().strip().strip(".!?,")
    if any(k in cleaned for k in ("def ", "import ", "python", "kod", "satır", "fonksiyon", "dosya", "class ")):
        return None

    # 1. Yüzde Hesaplama (Örn: "1500'ün yüzde 20'si", "500 liranın yüzde 18'i kaç eder")
    pct_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:'nin|'nın|'nun|'nün|'ün|'in|in|nin)?\s*(?:liranın|tl'nin)?\s*yüzde\s*(\d+(?:[.,]\d+)?)(?:'si|'sı|'su|'sü)?(?:\s+(?:kaç|kaçtır|eder|ne kadar))?",
        cleaned
    )
    if pct_match:
        try:
            base_val = float(pct_match.group(1).replace(",", "."))
            pct_val = float(pct_match.group(2).replace(",", "."))
            res = (base_val * pct_val) / 100.0
            res_str = f"{int(res)}" if res.is_integer() else f"{res:.2f}"
            base_str = f"{int(base_val)}" if base_val.is_integer() else f"{base_val}"
            pct_str = f"{int(pct_val)}" if pct_val.is_integer() else f"{pct_val}"
            suffix = _turkish_percent_suffix(pct_str)
            return f"{base_str} sayısının %{pct_str}{suffix} = {res_str} eder."
        except Exception:
            pass

    # 2. Standart Dört İşlem
    has_math = any(k in cleaned for k in (
        "çarpı", "kere", "bölü", "artı", "eksi", "üssü", "üzeri",
        "kaç eder", "kaçtır", "hesapla"
    ))
    if not has_math and not re.search(r"^\s*[\d\s\+\-\*\/\(\)\.\,]+\s*$", cleaned):
        return None

    expr = cleaned
    expr = re.sub(r"^(?:börü\s+)?(?:lütfen\s+)?(?:hesapla\s*:?|ne\s+kadar\s*:?)", "", expr)
    expr = re.sub(r"\s*(?:kaç\s+eder|kaçtır|ne\s+kadar|eder|sonucu\s+ne|sonucu\s+nedir)\s*$", "", expr)
    expr = expr.replace("çarpı", "*").replace("kere", "*")
    expr = expr.replace("bölü", "/").replace("bölüm", "/")
    expr = expr.replace("artı", "+").replace("eksi", "-")
    expr = expr.replace("üssü", "**").replace("üzeri", "**")
    expr = re.sub(r"(\d+),(\d+)", r"\1.\2", expr)

    if not re.search(r"[\d]", expr) or re.search(r"[^\d\s\+\-\*\/\(\)\.]", expr):
        return None

    try:
        val = _eval_ast_node(ast.parse(expr.strip(), mode="eval").body)
        val_str = f"{int(val)}" if isinstance(val, (int, float)) and float(val).is_integer() else f"{val:.4g}"
        disp_expr = expr.strip().replace("**", "^").replace("*", "×").replace("/", "÷")
        return f"{disp_expr} = {val_str} eder."
    except ZeroDivisionError:
        return "Sıfıra bölme işlemi tanımsızdır."
    except Exception:
        return None


def resolve_quick_info(user_text: str) -> Optional[str]:
    """
    Kullanıcının saat/tarih, matematik, hava durumu veya döviz kuru gibi
    hızlı bilgi sorularını anlık çözer.
    """
    cleaned = user_text.lower().strip().strip(".!?,")

    # 0. Zaman & Tarih Sorguları (Sıfır gecikmeli, %100 doğru sistem saati)
    # Saat soruları
    if any(k in cleaned for k in ("saat kaç", "şu an saat", "saati söyler", "saat kaç oldu", "bana saati söyle", "saat nedir")):
        return get_current_time_and_date("time")

    # Gün soruları ("bugün günlerden ne", "peki günlerden ne", "hangi gün")
    if any(k in cleaned for k in ("günlerden ne", "hangi gündeyiz", "hangi gün", "bugün hangi gün", "günü nedir")):
        return get_current_time_and_date("day")

    # Yıl soruları
    if any(k in cleaned for k in ("hangi yıldayız", "şu an hangi yıldayız", "kaç yılındayız")):
        return get_current_time_and_date("year")

    # Ay soruları
    if any(k in cleaned for k in ("hangi aydayız", "şu an hangi aydayız")):
        return get_current_time_and_date("month")

    # Tarih, Takvim & Gün-Ay-Yıl Sorguları ("bugünü gün ay yıl olarak göster", "ay gün yıl olarak", "tarih ne")
    if any(k in cleaned for k in (
        "bugünün tarihi", "bugün ayın kaçı", "tarih ne", "tarihi söyler", "tarih nedir",
        "günün tarihi", "hangi tarihteyiz", "tarihi göster", "tarih bilgisi",
        "gün ay yıl", "ay gün yıl", "yıl ay gün", "tarihi ver", "bugün tarih", "takvim"
    )) or cleaned in ("tarih", "tarih nedir", "tarih ne", "gün ay yıl", "ay gün yıl"):
        return get_current_time_and_date("date")

    # 0.1 Hızlı Matematik Hesaplamaları ("125 çarpı 48 kaç eder", "%18'i ne kadar")
    math_res = evaluate_math_expression(user_text)
    if math_res is not None:
        return math_res

    # 1. Hava Durumu Sorguları
    if any(k in cleaned for k in ("hava durumu", "hava nasıl", "kaç derece", "hava sıcaklığı")):
        target_city = None
        # 1.1 Öncelikli Doğrudan Eşleşme: Bilinen şehir listesi (uzunluk sırasına göre)
        for city in KNOWN_CITIES_SORTED:
            if re.search(rf"\b{re.escape(city)}", cleaned):
                target_city = city
                break

        # 1.2 Bilinenlerde yoksa regex dene (örn: "tokyo'da hava nasıl")
        if not target_city:
            city_match = re.search(r"([a-zğüşıöç]+)(?:'da|'de|'ta|'te|'daki|'deki)?\s+(?:hava\s+durumu|hava\s+nasıl)", cleaned)
            if city_match:
                cand = city_match.group(1).strip()
                STOPWORDS = {
                    "bugün", "yarın", "şu", "an", "bu", "o", "anki", "zaman",
                    "için", "bana", "lütfen", "durumu", "nasıl", "sıcaklığı",
                    "hava", "bir", "peki", "ise", "ve", "de", "da", "göre", "sonra"
                }
                if cand not in STOPWORDS and len(cand) >= 3:
                    target_city = cand

        if not target_city:
            try:
                from boru.learning import get_implicit_learner
                learned_city = get_implicit_learner().get_city()
                if learned_city:
                    target_city = learned_city
            except Exception:
                pass

        if not target_city:
            target_city = "Istanbul"

        ok, msg = get_weather(target_city)
        return msg

    # 2. Döviz & Altın Kuru Sorguları
    CURRENCY_TRIGGERS = [
        (["manat", "azn", "azerbaycan manatı", "azerbaycan manat"], "AZN"),
        (["dolar", "usd", "amerikan doları", "amerikan dolari"], "USD"),
        (["euro", "avro", "eur"], "EUR"),
        (["sterlin", "pound", "gbp", "ingiliz sterlini"], "GBP"),
        (["yen", "jpy", "japon yeni"], "JPY"),
        (["frank", "chf", "isviçre frangı", "isvicre frangi"], "CHF"),
        (["riyal", "sar", "suudi riyali", "suudi arabistan riyali"], "SAR"),
        (["dinar", "kwd", "kuveyt dinarı", "kuveyt dinari"], "KWD"),
        (["dirhem", "aed", "bae dirhemi"], "AED"),
        (["ruble", "rub", "rus rublesi"], "RUB"),
        (["yuan", "cny", "çin yuanı", "cin yuani"], "CNY"),
        (["kanada doları", "kanada dolari", "cad"], "CAD"),
        (["avustralya doları", "avustralya dolari", "aud"], "AUD"),
    ]

    # Altın kontrolü ("gram altın ne kadar", "çeyrek altın kaç tl")
    if any(k in cleaned for k in ("altın", "altin", "çeyrek", "ceyrek", "gram altın")):
        if any(k in cleaned for k in ("kaç", "kac", "ne kadar", "fiyat", "kur", "tl", "lira", "söyle")):
            try:
                from boru.tools.web_search import search_web_live
                ok_g, g_text = search_web_live("canlı gram altın çeyrek altın fiyatı kaç tl", max_results=1)
                if ok_g and g_text:
                    return f"Canlı Altın Piyasası:\n{g_text}"
            except Exception:
                pass

    # Döviz kurları kontrolü ("azerbaycan manatı ne kadar", "dolar kaç tl", "1 manat kaç lira")
    for keywords, iso_code in CURRENCY_TRIGGERS:
        for kw in keywords:
            if kw in cleaned:
                if any(q in cleaned for q in ("kur", "kaç", "kac", "ne kadar", "fiyat", "değer", "deger", "eder", "tl", "lira", "söyle", "nedir", "ne")) or cleaned in (kw, f"{kw} kuru"):
                    ok, msg = get_currency_rate(iso_code, "TRY")
                    return msg

    return None

