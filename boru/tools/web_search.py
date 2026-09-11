"""
boru.tools.web_search
=====================
Canli internet aramasi, guncel haberler ve web ozetleme motoru.
ddgs (DuckDuckGo Search) kutuphanesini oncelikli kullanir.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SEARCH_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
CACHE_TTL = 300.0


def search_web_live(query: str, max_results: int = 3) -> Tuple[bool, str]:
    q = query.strip()
    if not q:
        return False, "Arama sorgusu belirtilmedi."

    cache_key = q.lower()
    now = time.time()
    if cache_key in _SEARCH_CACHE:
        ts, cached_res = _SEARCH_CACHE[cache_key]
        if now - ts < CACHE_TTL:
            return True, _format_search_results(q, cached_res)

    results: List[Dict[str, str]] = []

    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(q, max_results=max_results))
            for r in raw_results:
                title = r.get("title", "").strip()
                body = r.get("body", "").strip()
                href = r.get("href", "").strip()
                if title and body:
                    results.append({"title": title, "body": body, "href": href})
    except Exception as e:
        logger.debug(f"DDGS arama hatasi ({q}): {e}")

    if results:
        _SEARCH_CACHE[cache_key] = (now, results)
        return True, _format_search_results(q, results)

    try:
        from boru.tools.web_qa_tools import search_wikipedia_summary
        ok, wiki_summary = search_wikipedia_summary(q)
        if ok and wiki_summary:
            return True, f"Web aramasinda one cikan bilgi:\n{wiki_summary}"
    except Exception:
        pass

    return False, f"'{q}' icin guncel arama sonucu bulunamadi."


def _format_search_results(query: str, results: List[Dict[str, str]]) -> str:
    if not results:
        return f"'{query}' icin sonuc bulunamadi."

    snippets = []
    for i, r in enumerate(results[:3], 1):
        title = r["title"]
        body = r["body"]
        clean_body = re.sub(r"\s+", " ", body).strip()
        if len(clean_body) > 220:
            clean_body = clean_body[:220].rsplit(" ", 1)[0] + "..."
        snippets.append(f"{i}. {title}: {clean_body}")

    joined = "\n\n".join(snippets)
    return f"🌐 '{query}' hakkinda canli web sonuclari:\n\n{joined}"


def resolve_web_search_command(user_text: str) -> Optional[str]:
    cleaned = user_text.lower().strip().strip(".!?,")

    patterns = [
        r"^(?:börü\s+)?(?:lütfen\s+)?(?:internette|webde|canlı|google'da|internetten)\s+(?:ara|arama\s+yap)\s*:?\s*(.+)$",
        r"^(?:börü\s+)?(?:lütfen\s+)?(?:ara|arama\s+yap)\s*:\s*(.+)$",
        r"^(?:börü\s+)?(?:lütfen\s+)?(?:ara|arama\s+yap)\s+(.+)$",
        r"^(?:börü\s+)?(?:lütfen\s+)?(.+?)\s+(?:hakkında\s+ara|internette\s+ara)$",
    ]

    for pat in patterns:
        m = re.match(pat, cleaned)
        if m:
            target = m.group(1).strip()
            if target and not any(k in target for k in ("bilgisayar", "uygulama", "müzik", "ses", "ekran", "not")):
                ok, res = search_web_live(target)
                if ok:
                    return res

    if any(k in cleaned for k in ("son dakika haber", "gündemde ne var", "türkiye gündemi", "güncel haberler")):
        ok, res = search_web_live("türkiye son dakika haberleri")
        if ok:
            return res

    return None
