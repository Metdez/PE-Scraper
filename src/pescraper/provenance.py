"""Quote-to-page matching for per-field provenance (``extractions.source_page_url``).

Code-side, never trusted from the model: a quote string is matched against the
fetched pages' text to determine which page it actually came from. A quote that
doesn't string-match (exactly or fuzzily) any page is unverified — returns None
rather than a guessed URL.
"""

from __future__ import annotations

import difflib


def find_source_page(
    quote: str | None, pages: dict[str, str], min_ratio: float = 0.6
) -> str | None:
    """Return the URL of the page whose text best matches ``quote``, or None.

    Exact-substring match (case-insensitive) is a cheap fast path. Otherwise the
    best ``difflib.SequenceMatcher.quick_ratio()`` across all pages is used, and
    only returned if it clears ``min_ratio``.
    """
    if not quote:
        return None

    quote_norm = quote.strip().lower()
    if not quote_norm:
        return None

    best_url: str | None = None
    best_ratio = 0.0
    for url, text in pages.items():
        text_norm = (text or "").lower()
        if quote_norm in text_norm:
            return url
        ratio = difflib.SequenceMatcher(None, quote_norm, text_norm).quick_ratio()
        if ratio > best_ratio:
            best_url, best_ratio = url, ratio

    return best_url if best_ratio >= min_ratio else None


__all__ = ["find_source_page"]
