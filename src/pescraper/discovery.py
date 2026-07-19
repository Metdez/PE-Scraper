"""Firm discovery and dead-URL recovery (Phase 7).

Windows-native pivot: Docker isn't installed on this machine, so this uses a
native free-metasearch fallback (DuckDuckGo's no-JS HTML endpoint, no API key,
zero cost) instead of self-hosted SearXNG — the explicit fallback path ROADMAP
left open for exactly this case. Swap ``search_web``'s implementation for a
SearXNG client later without touching callers if Docker becomes available.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

# DuckDuckGo's no-JS "Lite" endpoint — live-verified this session; the main
# html.duckduckgo.com/html/ endpoint returned an anomaly.js bot challenge for
# every request (even via a real headless browser), Lite did not.
SEARCH_URL = "https://lite.duckduckgo.com/lite/"

# Result anchors: <a href="//duckduckgo.com/l/?uddg=<encoded target>" ... class='result-link'>Title</a>
_RESULT_RE = re.compile(
    r"""<a[^>]+href="([^"]+)"[^>]+class='result-link'>(.*?)</a>""", re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")

PE_KEYWORDS = (
    "private equity",
    "capital partners",
    "growth equity",
    "buyout",
    "investment firm",
    "middle market",
    "management buyout",
)

DIRECTORY_DOMAINS = (
    "linkedin.com",
    "crunchbase.com",
    "bloomberg.com",
    "wikipedia.org",
    "facebook.com",
    "twitter.com",
    "x.com",
    "pitchbook.com",
    "sec.gov",
)


def _clean_ddg_redirect(href: str) -> str:
    """DuckDuckGo wraps result URLs in /l/?uddg=<encoded target>."""
    if "uddg=" in href:
        qs = parse_qs(urlparse(href).query)
        target = qs.get("uddg")
        if target:
            return unquote(target[0])
    return href


def search_web(query: str, max_results: int = 10, timeout: float = 15.0) -> list[dict]:
    """Query DuckDuckGo's HTML endpoint; returns [{"title": ..., "url": ...}].

    Never raises on network failure — returns [] and logs, matching the
    pipeline's "a search failure is not a crash" convention.
    """
    try:
        resp = httpx.get(SEARCH_URL, params={"q": query}, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) pescraper/0.1"
        })
        resp.raise_for_status()
    except Exception:
        logger.warning("search_web failed for query %r", query, exc_info=True)
        return []

    results = []
    for href, raw_title in _RESULT_RE.findall(resp.text):
        url = _clean_ddg_redirect(href)
        title = _TAG_RE.sub("", raw_title).strip()
        if url.startswith("http"):
            results.append({"title": title, "url": url})
        if len(results) >= max_results:
            break
    return results


def classify_pe_firm(name: str, snippet: str = "") -> bool:
    """Cheap keyword heuristic — no LLM call needed for this pass/fail signal."""
    text = f"{name} {snippet}".lower()
    return any(kw in text for kw in PE_KEYWORDS)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_directory_site(url: str) -> bool:
    domain = _domain(url)
    return any(domain == d or domain.endswith("." + d) for d in DIRECTORY_DOMAINS)


def dedupe_against_existing(
    candidates: list[dict], existing_names: set[str], existing_domains: set[str]
) -> list[dict]:
    """Filter out candidates already present by normalized name or domain."""
    seen_domains: set[str] = set()
    out = []
    for c in candidates:
        name_norm = c["title"].strip().lower()
        domain = _domain(c["url"])
        if name_norm in existing_names or domain in existing_domains or domain in seen_domains:
            continue
        if is_directory_site(c["url"]):
            continue
        seen_domains.add(domain)
        out.append(c)
    return out


def run_discovery(conn, queries: list[str], max_results_per_query: int = 10) -> int:
    """Search each query, classify/dedupe, queue genuine new firms as pending.

    Returns the count of newly queued firms.
    """
    from pescraper import db
    from pescraper.models import FirmRecord

    existing = db.all_firms(conn)
    existing_names = {r.firm_name.strip().lower() for r in existing}
    existing_domains = {_domain(r.website) for r in existing if r.website}

    queued = 0
    for query in queries:
        results = search_web(query, max_results=max_results_per_query)
        pe_only = [r for r in results if classify_pe_firm(r["title"])]
        new_candidates = dedupe_against_existing(pe_only, existing_names, existing_domains)

        for candidate in new_candidates:
            record = FirmRecord(firm_name=candidate["title"], website=candidate["url"])
            db.upsert_firm(conn, record)
            if not db.job_already_queued(conn, "run_firm", candidate["url"]):
                db.enqueue_job(conn, "run_firm", candidate["url"], priority=9)
            existing_names.add(candidate["title"].strip().lower())
            existing_domains.add(_domain(candidate["url"]))
            queued += 1

    return queued


def recover_dead_urls(conn) -> int:
    """Search for a new website for every firm whose website is null, and
    re-enter it into the queue. Returns count of URLs recovered."""
    from pescraper import db

    rows = conn.execute(
        "SELECT firm_name FROM firms WHERE website IS NULL OR website = ''"
    ).fetchall()

    recovered = 0
    for row in rows:
        firm_name = row["firm_name"]
        results = search_web(f"{firm_name} private equity official website", max_results=5)
        candidate = next((r for r in results if not is_directory_site(r["url"])), None)
        if candidate is None:
            continue
        conn.execute(
            "UPDATE firms SET website = ? WHERE firm_name = ?", (candidate["url"], firm_name)
        )
        conn.commit()
        if not db.job_already_queued(conn, "run_firm", candidate["url"]):
            db.enqueue_job(conn, "run_firm", candidate["url"], priority=9)
        recovered += 1

    return recovered


__all__ = [
    "SEARCH_URL",
    "PE_KEYWORDS",
    "DIRECTORY_DOMAINS",
    "search_web",
    "classify_pe_firm",
    "is_directory_site",
    "dedupe_against_existing",
    "run_discovery",
    "recover_dead_urls",
]
