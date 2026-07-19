"""AdaptiveCrawler page selection, skip-list, 403 fallback (PIPE-01).

RESEARCH.md "Pattern 1: AdaptiveCrawler — Correct API Usage", "Pattern 3: 403/Blocked-
Page Detection and Priority-Path Fallback", and the combined "Full single-page
decongestion + relevance filter" code example are the base shape for
:func:`select_pages`.

``select_pages(url)`` opens ONE ``AsyncWebCrawler`` async context for the whole call,
runs an adaptive, query-driven crawl (``AdaptiveCrawler.digest``), filters the top
relevant pages against a boilerplate skip-list, decongests each survivor's
``cleaned_html`` via :mod:`pescraper.decongest` (Pitfall 1 fix — ``AdaptiveCrawler``
does not decongest on its own), and — if nothing survives (e.g. a 403/blocked start
URL) — falls back to guessing well-known criteria-page paths on the same crawler.
Every network call is wrapped so exceptions are caught, logged, and treated as "this
path yielded nothing"; ``select_pages`` itself never raises. An empty return dict IS
the caller's "no_criteria_page" signal (CONTEXT.md) — no separate exception type.
"""

from __future__ import annotations

import logging

import tenacity
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.adaptive_crawler import AdaptiveConfig, AdaptiveCrawler

from pescraper import decongest, runtime

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
WELL_KNOWN_PATHS = ("/about", "/investment-criteria", "/strategy", "/approach")
QUERY = "investment criteria ebitda revenue enterprise value check size deal types"


@tenacity.retry(
    stop=tenacity.stop_after_attempt(2),
    wait=tenacity.wait_fixed(1),
    reraise=False,
)
async def _digest_with_retry(adaptive: AdaptiveCrawler, url: str):
    """One transient network blip must not kill the whole firm's crawl."""
    return await adaptive.digest(start_url=url, query=QUERY)


def _is_skip_listed(page_url: str) -> bool:
    lowered = page_url.lower()
    return any(keyword in lowered for keyword in SKIP_KEYWORDS)


async def select_pages(url: str) -> dict[str, str]:
    """Return ``{page_url: fit_markdown}`` for up to ~5 criteria-likely pages.

    Never raises — every failure mode (blocked start URL, digest exception, fallback
    fetch exception) degrades to "this source yielded nothing" and, on total failure,
    an empty dict.
    """
    pages: dict[str, str] = {}

    try:
        config = AdaptiveConfig(
            confidence_threshold=0.5,
            max_pages=5,
            top_k_links=3,
            strategy="statistical",
        )

        browser_config = BrowserConfig(**runtime.crawl4ai_browser_kwargs())
        async with AsyncWebCrawler(config=browser_config) as crawler:
            adaptive = AdaptiveCrawler(crawler, config=config)

            state = None
            try:
                state = await _digest_with_retry(adaptive, url)
            except Exception as exc:  # tenacity RetryError or a direct raise
                logger.warning("adaptive digest failed for %s (after retries): %r", url, exc)
                state = None

            if state is not None:
                try:
                    relevant = adaptive.get_relevant_content(top_k=5)
                except Exception as exc:
                    logger.warning("get_relevant_content failed for %s: %r", url, exc)
                    relevant = []

                by_url = {
                    result.url: result for result in (getattr(state, "knowledge_base", None) or [])
                }

                for item in relevant:
                    page_url = item.get("url")
                    if not page_url:
                        continue
                    if _is_skip_listed(page_url):
                        continue
                    if item.get("score", 0.0) <= 0.0:
                        continue

                    result = by_url.get(page_url)
                    cleaned_html = getattr(result, "cleaned_html", None) if result else None
                    if not cleaned_html:
                        continue

                    fit_markdown = decongest.decongest(cleaned_html, page_url)
                    if fit_markdown:
                        pages[page_url] = fit_markdown

            if not pages:
                base = url.rstrip("/")
                for path in WELL_KNOWN_PATHS:
                    candidate = base + path
                    try:
                        result = await crawler.arun(
                            url=candidate,
                            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=15000),
                        )
                    except Exception as exc:
                        logger.warning("fallback fetch failed for %s: %r", candidate, exc)
                        continue

                    cleaned_html = getattr(result, "cleaned_html", None)
                    if getattr(result, "success", False) and cleaned_html:
                        fit_markdown = decongest.decongest(cleaned_html, candidate)
                        if fit_markdown:
                            pages[candidate] = fit_markdown
    except Exception as exc:  # select_pages must never raise
        logger.warning("select_pages failed entirely for %s: %r", url, exc)
        return {}

    return pages
