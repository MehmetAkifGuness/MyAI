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
        encoded_loc = urllib.parse.quote_plus(clean_loc)
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
        logger.debug(f"Hava durumu çekme hatası: {e}")
        return False, "Hava durumu servisine şu anda ulaşılamıyor."


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
                currency_names = {
                    "USD": "Dolar",
                    "EUR": "Euro",
                    "GBP": "İngiliz Sterlini",
                    "TRY": "Türk Lirası",
                }
                base_name = currency_names.get(base_code, base_code)
                target_name = currency_names.get(target_code, target_code)
                result = f"1 {base_name} şu anda yaklaşık {val:.2f} {target_name} seviyesinde."
                _set_cached(cache_key, result)
                return True, result
    except Exception as e:
        logger.debug(f"Birincil döviz API hatası: {e}")

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
                result = f"1 {base_code} şu anda yaklaşık {val:.2f} {target_code} seviyesinde."
                _set_cached(cache_key, result)
                return True, result
    except Exception as e:
        logger.debug(f"Fallback döviz API hatası: {e}")

    return False, "Döviz kuru servisine şu anda ulaşılamıyor."


# Türkiye'nin popüler illeri (şehir çıkarımı için)
KNOWN_CITIES = [
    "istanbul", "ankara", "izmir", "bursa", "antalya", "adana", "konya",
    "gaziantep", "şanlıurfa", "kocaeli", "mersin", "diyarbakır", "hatay",
    "manisa", "kayseri", "samsun", "balıkesir", "kahramanmaraş", "van",
    "aydın", "tekirdağ", "denizli", "sakarya", "muğla", "eskişehir",
    "mardin", "malatya", "trabzon", "erzurum", "ordu", "afyon", "sivas",
    "rize", "edirne", "çanakkale", "zonguldak", "tokat", "elazığ"
]


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
        return f"Bugünün tarihi: {date_str}."
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

    # Gün soruları
    if any(k in cleaned for k in ("bugün günlerden ne", "hangi gündeyiz", "bugün hangi gün")):
        return get_current_time_and_date("day")

    # Yıl soruları
    if any(k in cleaned for k in ("hangi yıldayız", "şu an hangi yıldayız", "kaç yılındayız")):
        return get_current_time_and_date("year")

    # Ay soruları
    if any(k in cleaned for k in ("hangi aydayız", "şu an hangi aydayız")):
        return get_current_time_and_date("month")

    # Tarih soruları
    if any(k in cleaned for k in ("bugünün tarihi", "bugün ayın kaçı", "tarih ne", "tarihi söyler", "tarih nedir", "günün tarihi")):
        return get_current_time_and_date("date")

    # 0.1 Hızlı Matematik Hesaplamaları ("125 çarpı 48 kaç eder", "%18'i ne kadar")
    math_res = evaluate_math_expression(user_text)
    if math_res is not None:
        return math_res

    # 1. Hava Durumu Sorguları
    if any(k in cleaned for k in ("hava durumu", "hava nasıl", "kaç derece", "hava sıcaklığı")):
        target_city = "Istanbul"
        for city in KNOWN_CITIES:
            if city in cleaned:
                target_city = city
                break

        # Şehir belirleme regex (örn: "londra'da hava nasıl")
        city_match = re.search(r"([a-zğüşıöç]+)(?:'da|'de|'ta|'te|'daki|'deki)?\s+(?:hava\s+durumu|hava\s+nasıl)", cleaned)
        if city_match:
            cand = city_match.group(1).strip()
            if cand not in ("bugün", "yarın", "şu", "an", "bu"):
                target_city = cand

        ok, msg = get_weather(target_city)
        return msg

    # 2. Döviz Kuru Sorguları
    # Dolar (Her türlü serbest kalıp: "dolar kurunu söyler misin", "dolar kuru ne", "dolar kaç tl", "dolar ne kadar")
    if ("dolar" in cleaned and any(k in cleaned for k in ("kur", "kaç", "ne kadar", "söyle", "fiyat", "değer", "eder", "tl"))) or cleaned in ("dolar", "dolar kuru"):
        ok, msg = get_currency_rate("USD", "TRY")
        return msg

    # Euro / Avro
    if (any(k in cleaned for k in ("euro", "avro")) and any(k in cleaned for k in ("kur", "kaç", "ne kadar", "söyle", "fiyat", "değer", "eder", "tl"))) or cleaned in ("euro", "euro kuru", "avro"):
        ok, msg = get_currency_rate("EUR", "TRY")
        return msg

    # Sterlin / Pound
    if any(k in cleaned for k in ("sterlin", "pound")) and any(k in cleaned for k in ("kur", "kaç", "ne kadar", "söyle", "fiyat", "tl")):
        ok, msg = get_currency_rate("GBP", "TRY")
        return msg

    return None

