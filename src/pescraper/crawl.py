"""AdaptiveCrawler page selection: skip-lists, relevance filtering, 403 fallback.

The pipeline's first step (RESEARCH.md Pattern 1/3, Code Examples). Returns
``{page_url: fit_markdown}`` for up to ~5 criteria-likely pages. An empty dict is
the caller's "no_criteria_page" signal — this module never raises.
"""

from __future__ import annotations

import logging

import tenacity

from pescraper import decongest

logger = logging.getLogger(__name__)

SKIP_KEYWORDS = (
    "team",
    "portfolio",
    "news",
    "press",
    "blog",
    "insights",
    "careers",
    "legal",
    "privacy",
    "terms",
)
WELL_KNOWN_PATHS = (
    "/about",
    "/investment-criteria",
    "/strategy",
    "/strategies",
    "/approach",
    "/what-we-look-for",
    "/criteria",
)
QUERY = "investment criteria ebitda revenue enterprise value check size deal types"


async def _digest_with_retry(adaptive, url: str, query: str):
    """Run AdaptiveCrawler.digest() with a short retry, never raising on failure."""

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(2),
        wait=tenacity.wait_fixed(1),
        reraise=True,
    )
    async def _attempt():
        return await adaptive.digest(start_url=url, query=query)

    try:
        return await _attempt()
    except Exception:
        logger.warning("AdaptiveCrawler.digest failed for %s", url, exc_info=True)
        return None


async def select_pages(url: str) -> dict[str, str]:
    """Select up to ~5 criteria-likely pages for ``url``, decongested, skip-listed.

    Never raises. Empty dict means no relevant page was found (caller flags
    needs_review with a "no_criteria_page" reason).
    """
    from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
    from crawl4ai.adaptive_crawler import AdaptiveConfig, AdaptiveCrawler

    pages: dict[str, str] = {}

    try:
        async with AsyncWebCrawler() as crawler:
            config = AdaptiveConfig(
                confidence_threshold=0.5,
                max_pages=5,
                top_k_links=3,
                strategy="statistical",
            )
            adaptive = AdaptiveCrawler(crawler, config=config)
            state = await _digest_with_retry(adaptive, url, QUERY)

            if state is not None:
                try:
                    relevant = adaptive.get_relevant_content(top_k=5)
                    by_url = {r.url: r for r in state.knowledge_base}
                except Exception:
                    logger.warning("relevance extraction failed for %s", url, exc_info=True)
                    relevant = []
                    by_url = {}

                for item in relevant:
                    page_url = item["url"]
                    if any(kw in page_url.lower() for kw in SKIP_KEYWORDS):
                        continue
                    if item.get("score", 0) <= 0:
                        continue
                    result = by_url.get(page_url)
                    if result is None or not getattr(result, "cleaned_html", None):
                        continue
                    fit_markdown = decongest.decongest(result.cleaned_html, page_url)
                    if fit_markdown:
                        pages[page_url] = fit_markdown

            # Augment thin adaptive results, not just empty ones: on real PE
            # marketing sites the adaptive crawl often "succeeds" by settling on
            # a low-value page (e.g. a portfolio/investments listing) that scores
            # marginally above zero without ever surfacing an actual criteria
            # page — live-verified this session (RESEARCH.md Open Question 1).
            # Always also probe the well-known criteria paths when coverage is
            # thin (<2 pages), merging in any genuine hits alongside whatever
            # adaptive already found, rather than only as a total-failure fallback.
            if len(pages) < 2:
                base = url.rstrip("/")
                for path in WELL_KNOWN_PATHS:
                    candidate = base + path
                    if candidate in pages:
                        continue
                    try:
                        result = await crawler.arun(
                            url=candidate,
                            config=CrawlerRunConfig(
                                cache_mode=CacheMode.BYPASS, page_timeout=15000
                            ),
                        )
                    except Exception:
                        logger.warning(
                            "fallback fetch failed for %s", candidate, exc_info=True
                        )
                        continue
                    if getattr(result, "success", False) and getattr(
                        result, "cleaned_html", None
                    ):
                        fit_markdown = decongest.decongest(result.cleaned_html, candidate)
                        if fit_markdown:
                            pages[candidate] = fit_markdown
    except Exception:
        logger.warning("select_pages failed entirely for %s", url, exc_info=True)
        return {}

    return pages


__all__ = ["SKIP_KEYWORDS", "WELL_KNOWN_PATHS", "QUERY", "select_pages"]
