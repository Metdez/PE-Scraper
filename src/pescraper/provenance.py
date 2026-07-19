"""Quote-to-page matching for per-field provenance (source_page_url).

Per 02-RESEARCH.md "Pattern 6: Per-Field Provenance via Code-Side Quote
Matching": rather than trust a small model to echo back an arbitrary URL
verbatim, the model returns a verbatim quote alongside each extracted value,
and this module string-matches that quote against the fetched pages' text to
determine which page it came from — deterministic, code-side, stdlib only.
"""

from __future__ import annotations

import difflib
from typing import Optional


def find_source_page(
    quote: Optional[str], pages: dict[str, str], min_ratio: float = 0.6
) -> Optional[str]:
    """Return the URL of the page whose text best matches ``quote``, or None.

    Normalizes quote and page text to lowercase. If the normalized quote is a
    substring of a page's normalized text, returns that URL immediately (cheap
    exact fast path). Otherwise, for each page, first checks
    ``difflib.SequenceMatcher.quick_ratio()`` — a fast O(n) upper bound on the
    real ratio — and skips the page immediately if even that upper bound
    can't clear ``min_ratio`` (guarantees the true ratio would also miss, so
    this stays a cheap rejection for the common no-match case per the threat
    model's DoS mitigation). Only pages whose quick_ratio clears the
    threshold pay for the more expensive, accurate
    ``SequenceMatcher.ratio()`` call, since quick_ratio is known to
    overestimate similarity for short, character-overlapping strings. Returns
    the URL with the best confirmed ratio, if it clears ``min_ratio``; else
    None.

    A quote that doesn't string-match (exactly or well enough) any fetched
    page's text returns None (unverified) rather than a guessed URL.
    """
    if not quote:
        return None

    quote_norm = quote.strip().lower()
    if not quote_norm:
        return None

    best_url: Optional[str] = None
    best_ratio = 0.0
    for url, text in pages.items():
        text_norm = (text or "").lower()
        if quote_norm in text_norm:
            return url  # exact substring — cheap fast path, short-circuits fuzzy scan
        matcher = difflib.SequenceMatcher(None, quote_norm, text_norm)
        if matcher.quick_ratio() < min_ratio:
            continue  # quick_ratio is an upper bound; real ratio can't clear threshold either
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_url, best_ratio = url, ratio

    return best_url if best_ratio >= min_ratio else None


__all__ = ["find_source_page"]
