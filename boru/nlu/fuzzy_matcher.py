"""Fuzzy matching, typographical error tolerance and Turkish text normalization.

Enables Börü to recognize user commands and intents even when written with typos,
missing letters, transposed letters, or non-standard Turkish diacritics.
"""

from typing import Sequence


_TURKISH_MAP = {
    "İ": "i",
    "I": "ı",
    "ı": "i",
    "ş": "s",
    "Ş": "s",
    "ç": "c",
    "Ç": "c",
    "ğ": "g",
    "Ğ": "g",
    "ö": "o",
    "Ö": "o",
    "ü": "u",
    "Ü": "u",
}


def normalize_turkish(text: str) -> str:
    """Normalize Turkish characters to lowercase ASCII equivalents for resilient comparison."""
    if not text:
        return ""
    return "".join(_TURKISH_MAP.get(char, char.lower()) for char in text)


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Damerau-Levenshtein distance between two strings.

    Supports insertion, deletion, substitution, and transposition of adjacent characters.
    """
    len1, len2 = len(s1), len(s2)
    d = {}
    for i in range(-1, len1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len2 + 1):
        d[(-1, j)] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,        # deletion
                d[(i, j - 1)] + 1,        # insertion
                d[(i - 1, j - 1)] + cost, # substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + cost)  # transposition

    return d[(len1 - 1, len2 - 1)]


def match_command_prefix(
    message: str,
    candidate_triggers: Sequence[str],
    max_distance: int = 2,
) -> tuple[str, str] | None:
    """Match a user message against command triggers with typo tolerance.

    Returns:
        tuple[canonical_trigger, payload] if a match is found, else None.
    """
    cleaned = message.strip()
    if not cleaned:
        return None

    # Case 1: Explicit colon delimiter, e.g. "kdola: main.py incele" or "kodla : foo"
    if ":" in cleaned:
        prefix, _, body = cleaned.partition(":")
        norm_prefix = normalize_turkish(prefix.strip())
        for trigger in candidate_triggers:
            norm_trigger = normalize_turkish(trigger)
            # For short triggers (<= 4 chars), tolerate at most 1 typo. For longer, up to max_distance.
            allowed = 1 if len(norm_trigger) <= 4 else max_distance
            dist = damerau_levenshtein_distance(norm_prefix, norm_trigger)
            if dist <= allowed:
                return trigger, body.strip()

    # Case 2: Colon-less command at line start, e.g. "kdola main.py incele"
    words = cleaned.split()
    if len(words) >= 2:
        for num_words in (3, 2, 1):
            if len(words) >= num_words:
                prefix = " ".join(words[:num_words])
                norm_prefix = normalize_turkish(prefix)
                # Do not match noun/plural inflections as imperative commands
                if norm_prefix.endswith(("lar", "ler", "dan", "den", "dir", "dur", "dur")):
                    continue
                for trigger in candidate_triggers:
                    norm_trigger = normalize_turkish(trigger)
                    # Do not treat words that simply extend the trigger with extra letters as a typo
                    if norm_prefix.startswith(norm_trigger) and len(norm_prefix) > len(norm_trigger):
                        continue
                    allowed = 0 if len(norm_trigger) <= 4 else 1
                    dist = damerau_levenshtein_distance(norm_prefix, norm_trigger)
                    if dist <= allowed:
                        body = " ".join(words[num_words:])
                        return trigger, body.strip()

    return None


def locate_unique_fuzzy_slice(original: str, old_text: str) -> tuple[int, int] | None:
    """Locate the exact (start_idx, end_idx) character slice in original that corresponds
    to old_text, tolerating minor newline (CRLF vs LF), trailing whitespace, and blank line discrepancies.

    Returns:
        tuple[int, int] containing start and end indices in original if exactly one unambiguous match exists.
        None if no match or multiple ambiguous matches are found.
    """
    if not original or not old_text:
        return None

    # 1. Fast exact match check
    exact_count = original.count(old_text)
    if exact_count == 1:
        start = original.find(old_text)
        return start, start + len(old_text)
    if exact_count > 1:
        return None

    # 2. Line-based normalized matching
    orig_lines = original.splitlines(keepends=True)
    old_lines = old_text.strip("\r\n").splitlines()

    if not old_lines or not orig_lines:
        return None

    norm_orig = [line.rstrip("\r\n").rstrip() for line in orig_lines]
    norm_old = [line.rstrip("\r\n").rstrip() for line in old_lines]

    matches = []
    len_old = len(norm_old)
    for i in range(len(norm_orig) - len_old + 1):
        if norm_orig[i : i + len_old] == norm_old:
            matches.append(i)

    if len(matches) == 1:
        match_idx = matches[0]
        start_char = sum(len(line) for line in orig_lines[:match_idx])
        matched_chars = sum(len(line) for line in orig_lines[match_idx : match_idx + len_old])
        return start_char, start_char + matched_chars

    return None
