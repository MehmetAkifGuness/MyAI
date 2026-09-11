"""
boru.tools.compound_tools
=========================
Doğal dilde verilen çoklu / zincirleme komutları ("ve", "ardından", "sonra")
akıllıca ayrıştırıp sırayla yürüten ve birleşik yanıt üreten modül.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

COMPOUND_DELIMITERS = [
    r"\s*,\s*(?:ardından|daha sonra|sonra)\s*",
    r"\s+(?:ardından|daha sonra)\s+",
    r"\s*,\s*ve\s+",
    r"\s+ve\s+(?:sonra\s+|ardından\s+)?",
    r"\s*,\s*bir de\s+",
    r"\s+bir de\s+",
    r"\s*;\s*",
]

_COMBINED_DELIM_PATTERN = re.compile(
    "|".join(f"(?:{p})" for p in COMPOUND_DELIMITERS),
    re.IGNORECASE,
)


def split_compound_commands(text: str) -> List[str]:
    """
    Kullanıcı cümlesini bağlaçlardan parçalayarak olası alt komutlara böler.
    Eğer cümle tırnak işareti veya özel bloklar içeriyorsa bunları korur.
    """
    raw = text.strip()
    if not raw:
        return []

    placeholders: dict[str, str] = {}
    def _mask_quotes(match: re.Match) -> str:
        key = f"__STR_TOKEN_{len(placeholders)}__"
        placeholders[key] = match.group(0)
        return key

    masked = re.sub(r'["\'].+?["\']', _mask_quotes, raw)

    parts = _COMBINED_DELIM_PATTERN.split(masked)
    cleaned_parts: List[str] = []

    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        for key, val in placeholders.items():
            chunk = chunk.replace(key, val)
        cleaned_parts.append(chunk)

    return cleaned_parts


def resolve_compound_commands(
    user_text: str,
    resolver_fn: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[str]:
    """
    Eğer kullanıcı mesajı birden çok bağımsız sistem komutu içeriyorsa
    (örn: 'müziği durdur ve masaüstünü göster') her birini sırayla yürütür
    ve birleşik bir onay mesajı döndürür.

    Eğer cümle tek bir bütün olarak çözülebiliyorsa veya parçalardan biri
    sistem komutu değilse None döndürür (böylece tekil akış veya LLM bozulmaz).
    """
    cleaned = user_text.strip()
    if not cleaned:
        return None

    if resolver_fn is None:
        from boru.tools.system_tools import resolve_system_command
        resolver_fn = resolve_system_command

    single_res = resolver_fn(cleaned)
    if single_res is not None:
        return None

    chunks = split_compound_commands(cleaned)
    if len(chunks) < 2:
        return None

    resolved_answers: List[str] = []
    for chunk in chunks:
        answer = resolver_fn(chunk)
        if answer is None:
            return None
        resolved_answers.append(answer.strip())

    if len(resolved_answers) != len(chunks):
        return None

    clean_items = [ans.rstrip(".!?,") for ans in resolved_answers]
    if len(clean_items) == 2:
        return f"{clean_items[0]} ve {clean_items[1].lower()}."
    else:
        return ", ".join(clean_items[:-1]) + f" ve {clean_items[-1].lower()}."
