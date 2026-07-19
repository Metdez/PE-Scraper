"""Manual HTML decongestion (fit_markdown) + content hashing.

RESEARCH.md "Pattern 2: fit_markdown Must Be Computed Manually (Critical Correction)":
``AdaptiveCrawler.get_relevant_content()``'s ``content`` field is ``raw_markdown``, not
decongested. On crawl4ai 0.9.2, ``AdaptiveCrawler._crawl_with_preview`` hard-codes its
own internal ``CrawlerRunConfig`` with no ``markdown_generator`` override, so
``fit_markdown`` on pages it fetches is always an empty string. This module runs the
decongestion step manually, as a separate call against each selected page's
``cleaned_html`` (already present on the ``CrawlResult`` objects in
``AdaptiveCrawler.state.knowledge_base``).

Zero network/browser dependency — pure HTML-string transformation, so its tests run
fully offline against real local HTML strings (no mocking needed).
"""

from __future__ import annotations

import hashlib
import logging

from crawl4ai import DefaultMarkdownGenerator, PruningContentFilter

logger = logging.getLogger(__name__)


def decongest(cleaned_html: str, base_url: str) -> str:
    """Return decongested ``fit_markdown`` for one page's already-fetched HTML.

    Uses ``DefaultMarkdownGenerator(content_filter=PruningContentFilter(threshold=0.48,
    threshold_type="fixed"))`` exactly per RESEARCH.md's Pattern 2. Never raises — a
    decongestion failure on one page must not crash the whole ``run-firm`` call; on any
    generator error, logs a warning and returns ``""``. Empty input always returns
    ``""`` without invoking the generator.
    """
    if not cleaned_html:
        return ""

    try:
        generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.48, threshold_type="fixed")
        )
        result = generator.generate_markdown(input_html=cleaned_html, base_url=base_url)
        return result.fit_markdown or ""
    except Exception as exc:  # never raise — caller treats this page as unusable
        logger.warning("decongest failed for %s: %r", base_url, exc)
        return ""


def content_hash(text: str) -> str:
    """Deterministic sha256 hexdigest of ``text`` (64-char lowercase hex)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
