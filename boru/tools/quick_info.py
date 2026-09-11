from __future__ import annotations

import json
import logging
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
    Frankfurter API üzerinden anlık resmi döviz kurunu çeker.
    """
    base_code = base.upper().strip()
    target_code = target.upper().strip()
    cache_key = f"fx_{base_code}_{target_code}"
    cached = _get_cached(cache_key)
    if cached:
        return True, cached

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

        return False, f"{base_code} kuru alınamadı."
    except Exception as e:
        logger.debug(f"Döviz kuru çekme hatası: {e}")
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


def resolve_quick_info(user_text: str) -> Optional[str]:
    """
    Kullanıcının hava durumu veya döviz kuru gibi hızlı bilgi sorularını çözümler.
    Eşleşirse doğrudan söylenecek metni döndürür. Eşleşmezse None döner.
    """
    cleaned = user_text.lower().strip().strip(".!?,")

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
    # Dolar
    if re.search(r"\b(?:dolar(?:ın)?|1\s*dolar)\b.*\b(?:kaç|ne kadar|fiyatı|kuru|seviyesinde)\b", cleaned) or cleaned in ("dolar", "dolar kuru", "dolar kaç tl", "dolar ne kadar"):
        ok, msg = get_currency_rate("USD", "TRY")
        return msg

    # Euro
    if re.search(r"\b(?:euro(?:nun)?|avro(?:nun)?|1\s*euro)\b.*\b(?:kaç|ne kadar|fiyatı|kuru|seviyesinde)\b", cleaned) or cleaned in ("euro", "euro kuru", "euro kaç tl", "euro ne kadar", "avro"):
        ok, msg = get_currency_rate("EUR", "TRY")
        return msg

    # Sterlin
    if re.search(r"\b(?:sterlin(?:in)?|pound(?:un)?)\b.*\b(?:kaç|ne kadar|fiyatı|kuru)\b", cleaned):
        ok, msg = get_currency_rate("GBP", "TRY")
        return msg

    return None

