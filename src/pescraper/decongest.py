"""Manual fit_markdown generation + content hashing.

crawl4ai 0.9.2's ``AdaptiveCrawler`` does NOT decongest content automatically —
``get_relevant_content()``'s ``content`` field is ``raw_markdown``, not
``fit_markdown`` (RESEARCH.md Pattern 2, live-verified). This module is the
explicit, separate decongestion step every selected page's ``cleaned_html`` must
pass through before it reaches the extraction prompt.
"""

from __future__ import annotations

import hashlib
import logging

from crawl4ai import DefaultMarkdownGenerator, PruningContentFilter

logger = logging.getLogger(__name__)


def decongest(cleaned_html: str, base_url: str) -> str:
    """Return decongested fit_markdown for one page's cleaned_html.

    Never raises: any generator error is logged and yields "". Empty input
    yields "" without invoking the generator.
    """
    if not cleaned_html:
        return ""
    try:
        generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.48, threshold_type="fixed")
        )
        result = generator.generate_markdown(input_html=cleaned_html, base_url=base_url)
        return result.fit_markdown or ""
    except Exception:
        logger.warning("decongest failed for %s", base_url, exc_info=True)
        return ""


def content_hash(text: str) -> str:
    """Deterministic sha256 hex digest of ``text`` (UTF-8 encoded)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = ["decongest", "content_hash"]
