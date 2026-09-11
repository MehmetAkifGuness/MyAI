"""
boru.tools.web_qa_tools
=======================
Tarayıcı penceresi açmadan, doğrudan arka planda çalışan sıfır gecikmeli
canlı internet ve ansiklopedi bilgi motoru (Wikipedia REST API & DuckDuckGo).
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 10 dakikalık bellek önbelleği
_QA_CACHE: Dict[str, Tuple[float, str]] = {}
QA_CACHE_TTL_SECONDS = 600.0


def _get_cached_answer(query: str) -> Optional[str]:
    entry = _QA_CACHE.get(query.lower().strip())
    if entry:
        timestamp, val = entry
        if time.time() - timestamp < QA_CACHE_TTL_SECONDS:
            return val
    return None


def _set_cached_answer(query: str, val: str) -> None:
    _QA_CACHE[query.lower().strip()] = (time.time(), val)


def search_wikipedia_summary(topic: str) -> Tuple[bool, str]:
    """
    Belirtilen konu veya kişi hakkında Türkçe Vikipedi özetini çeker.
    """
    clean_topic = topic.strip().strip("?.!\"'")
    if not clean_topic:
        return False, "Arama konusu boş olamaz."

    cached = _get_cached_answer(clean_topic)
    if cached:
        return True, cached

    try:
        # 1. Doğrudan sayfa özetini dene
        encoded_topic = urllib.parse.quote(clean_topic)
        url = f"https://tr.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BoruAI/14.0 (Personal AI Assistant; Contact: local@assistant)",
                "Accept-Language": "tr-TR,tr;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                extract = data.get("extract", "").strip()
                if extract:
                    # İlk 2-3 cümleyi al (aşırı uzun konuşmayı önlemek için)
                    sentences = re.split(r"(?<=[.!?])\s+", extract)
                    summary = " ".join(sentences[:3])
                    _set_cached_answer(clean_topic, summary)
                    return True, summary
        except urllib.error.HTTPError as he:
            if he.code != 404:
                raise he

        # 2. Eğer doğrudan bulunamadıysa arama API'siyle en alakalı başlığı bul
        search_url = (
            f"https://tr.wikipedia.org/w/api.php?action=query&list=search&srsearch="
            f"{urllib.parse.quote(clean_topic)}&format=json&utf8=1&srlimit=1"
        )
        s_req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "BoruAI/14.0 (Personal AI Assistant)"},
        )
        with urllib.request.urlopen(s_req, timeout=3.5) as s_resp:
            s_data = json.loads(s_resp.read().decode("utf-8", errors="replace"))
            search_results = s_data.get("query", {}).get("search", [])
            if search_results:
                best_title = search_results[0].get("title")
                if best_title:
                    # En iyi başlığın özetini çek
                    sub_url = f"https://tr.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(best_title)}"
                    sub_req = urllib.request.Request(
                        sub_url,
                        headers={"User-Agent": "BoruAI/14.0 (Personal AI Assistant)"},
                    )
                    with urllib.request.urlopen(sub_req, timeout=3.5) as sub_resp:
                        sub_data = json.loads(sub_resp.read().decode("utf-8", errors="replace"))
                        extract = sub_data.get("extract", "").strip()
                        if extract:
                            sentences = re.split(r"(?<=[.!?])\s+", extract)
                            summary = " ".join(sentences[:3])
                            _set_cached_answer(clean_topic, summary)
                            return True, summary

        return False, f"'{clean_topic}' hakkında doğrulanmış bir ansiklopedi kaydı bulunamadı."
    except Exception as e:
        logger.debug(f"Wikipedia bilgi çekme hatası ({topic}): {e}")
        return False, f"Bilgi servisine şu anda ulaşılamıyor."


def resolve_web_qa_command(user_text: str) -> Optional[str]:
    """
    Kullanıcının 'kimdir', 'nedir' veya 'hakkında bilgi ver' sorularını tanır ve seslendirir.
    Örnekler:
      - 'Atatürk kimdir?'
      - 'Barış Manço kimdir'
      - 'Kuantum bilgisayar nedir?'
      - 'Python nedir?'
      - 'Yapay zeka hakkında bilgi ver'
    """
    cleaned = user_text.lower().strip().strip("?!.,")

    # Sistem komutlarını ve özel durumları filtrele
    if any(k in cleaned for k in (
        "ram", "bellek", "pil", "şarj", "ses", "müzik", "masaüstü", "ekran",
        "hava durumu", "dolar", "euro", "notlarım", "not al", "kapat", "aç"
    )):
        return None

    # 1. "X kimdir?", "X nedir?", "X neresidir?", "X hangisidir?"
    match_who_what = re.match(r"^(?:börü\s+)?(?:lütfen\s+)?(?:bana\s+)?(.+?)\s+(kimdir|nedir|neresidir|hangisidir)$", cleaned)
    if match_who_what:
        query = match_who_what.group(1).strip()
        # "bu nedir", "o kimdir", "şu nedir" gibi belirsiz zamirleri ele
        if len(query) >= 2 and query not in ("bu", "o", "şu", "kim", "ne", "neresi", "hangisi"):
            ok, summary = search_wikipedia_summary(query)
            if ok:
                return summary

            # Wikipedia'da bulunamadıysa canlı DuckDuckGo web aramasına devret
            try:
                from boru.tools.web_search import search_web_live
                ok_web, web_res = search_web_live(f"{query} {match_who_what.group(2)}")
                if ok_web:
                    return web_res
            except Exception as e:
                logger.debug(f"Web fallback arama hatası: {e}")

    # 2. "X hakkında bilgi ver" veya "X hakkında bilgi"
    match_about = re.match(r"^(?:börü\s+)?(?:bana\s+)?(.+?)\s+(?:hakkında|ile ilgili)\s+bilgi(?:\s+ver)?$", cleaned)
    if match_about:
        query = match_about.group(1).strip()
        if len(query) >= 2 and query not in ("bu", "o", "şu"):
            ok, summary = search_wikipedia_summary(query)
            if ok:
                return summary

            try:
                from boru.tools.web_search import search_web_live
                ok_web, web_res = search_web_live(f"{query} hakkında bilgi")
                if ok_web:
                    return web_res
            except Exception as e:
                logger.debug(f"Web fallback arama hatası: {e}")

    return None

