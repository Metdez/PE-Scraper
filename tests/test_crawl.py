"""Offline tests for crawl.select_pages — mocks AsyncWebCrawler/AdaptiveCrawler
per RESEARCH.md's "monkeypatch to lock contract shape" pattern. No real network
or browser is touched.
"""

from __future__ import annotations

import asyncio

import pescraper.crawl as crawl_mod


class FakeCrawlResult:
    def __init__(self, url: str, cleaned_html: str = "<p>content</p>", success: bool = True):
        self.url = url
        self.cleaned_html = cleaned_html
        self.success = success
        self.error_message = ""


class FakeAdaptiveState:
    def __init__(self, knowledge_base: list[FakeCrawlResult]):
        self.knowledge_base = knowledge_base


class FakeAdaptiveCrawler:
    """Stands in for crawl4ai.adaptive_crawler.AdaptiveCrawler."""

    def __init__(self, crawler, config=None, *, relevant=None, results=None, raise_on_digest=False):
        self._crawler = crawler
        self._relevant = relevant or []
        self._results = results or []
        self._raise_on_digest = raise_on_digest

    async def digest(self, start_url: str, query: str):
        if self._raise_on_digest:
            raise RuntimeError("simulated digest failure")
        return FakeAdaptiveState(self._results)

    def get_relevant_content(self, top_k: int = 5):
        return self._relevant


def make_fake_adaptive_crawler_factory(*, relevant=None, results=None, raise_on_digest=False):
    def factory(crawler, config=None):
        return FakeAdaptiveCrawler(
            crawler,
            config=config,
            relevant=relevant,
            results=results,
            raise_on_digest=raise_on_digest,
        )

    return factory


class FakeAsyncWebCrawler:
    """Stands in for crawl4ai.AsyncWebCrawler as an async context manager."""

    def __init__(self, *args, **kwargs):
        self.fallback_results: dict[str, FakeCrawlResult] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def arun(self, url: str, config=None):
        return self.fallback_results.get(url, FakeCrawlResult(url, success=False, cleaned_html=""))


def _patch_crawl4ai(monkeypatch, *, adaptive_factory, fallback_results=None):
    import crawl4ai
    import crawl4ai.adaptive_crawler as adaptive_mod

    fake_crawler_instance = FakeAsyncWebCrawler()
    fake_crawler_instance.fallback_results = fallback_results or {}

    def fake_async_web_crawler(*args, **kwargs):
        return fake_crawler_instance

    monkeypatch.setattr(crawl4ai, "AsyncWebCrawler", fake_async_web_crawler)
    monkeypatch.setattr(adaptive_mod, "AdaptiveCrawler", adaptive_factory)
    return fake_crawler_instance


def test_select_pages_skip_list_excludes_team_keeps_about(monkeypatch) -> None:
    monkeypatch.setattr(
        crawl_mod.decongest, "decongest", lambda html, url: f"FIT:{html}"
    )
    team_result = FakeCrawlResult("https://a.example/team")
    about_result = FakeCrawlResult("https://a.example/about")
    relevant = [
        {"url": "https://a.example/team", "score": 0.9},
        {"url": "https://a.example/about", "score": 0.8},
    ]
    _patch_crawl4ai(
        monkeypatch,
        adaptive_factory=make_fake_adaptive_crawler_factory(
            relevant=relevant, results=[team_result, about_result]
        ),
    )

    pages = asyncio.run(crawl_mod.select_pages("https://a.example"))

    assert "https://a.example/team" not in pages
    assert "https://a.example/about" in pages


def test_select_pages_falls_back_to_well_known_paths_when_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        crawl_mod.decongest, "decongest", lambda html, url: f"FIT:{html}"
    )
    fallback_results = {
        "https://a.example/about": FakeCrawlResult(
            "https://a.example/about", cleaned_html="<p>about us</p>", success=True
        ),
        "https://a.example/investment-criteria": FakeCrawlResult(
            "https://a.example/investment-criteria", success=False, cleaned_html=""
        ),
        "https://a.example/strategy": FakeCrawlResult(
            "https://a.example/strategy", success=False, cleaned_html=""
        ),
        "https://a.example/approach": FakeCrawlResult(
            "https://a.example/approach", success=False, cleaned_html=""
        ),
    }
    _patch_crawl4ai(
        monkeypatch,
        adaptive_factory=make_fake_adaptive_crawler_factory(relevant=[], results=[]),
        fallback_results=fallback_results,
    )

    pages = asyncio.run(crawl_mod.select_pages("https://a.example"))

    assert "https://a.example/about" in pages
    assert pages["https://a.example/about"] == "FIT:<p>about us</p>"


def test_select_pages_total_failure_returns_empty_dict_never_raises(monkeypatch) -> None:
    monkeypatch.setattr(
        crawl_mod.decongest, "decongest", lambda html, url: f"FIT:{html}"
    )
    _patch_crawl4ai(
        monkeypatch,
        adaptive_factory=make_fake_adaptive_crawler_factory(raise_on_digest=True),
        fallback_results={},  # every fallback path also fails (default success=False)
    )

    pages = asyncio.run(crawl_mod.select_pages("https://a.example"))

    assert pages == {}


def test_select_pages_augments_thin_adaptive_result_with_well_known_paths(monkeypatch) -> None:
    # Adaptive finds exactly one (low-value) page — thin coverage (<2) should
    # still trigger a well-known-path probe, merged in alongside it.
    monkeypatch.setattr(
        crawl_mod.decongest, "decongest", lambda html, url: f"FIT:{html}"
    )
    investments_result = FakeCrawlResult("https://a.example/investments")
    relevant = [{"url": "https://a.example/investments", "score": 0.2}]
    fallback_results = {
        "https://a.example/strategy": FakeCrawlResult(
            "https://a.example/strategy", cleaned_html="<p>our strategy</p>", success=True
        ),
    }
    _patch_crawl4ai(
        monkeypatch,
        adaptive_factory=make_fake_adaptive_crawler_factory(
            relevant=relevant, results=[investments_result]
        ),
        fallback_results=fallback_results,
    )

    pages = asyncio.run(crawl_mod.select_pages("https://a.example"))

    assert "https://a.example/investments" in pages
    assert "https://a.example/strategy" in pages


def test_select_pages_content_passes_through_decongestion(monkeypatch) -> None:
    calls: list[str] = []

    def fake_decongest(html, url):
        calls.append(url)
        return f"FIT:{html}"

    monkeypatch.setattr(crawl_mod.decongest, "decongest", fake_decongest)
    about_result = FakeCrawlResult(
        "https://a.example/about", cleaned_html="<p>criteria</p>"
    )
    relevant = [{"url": "https://a.example/about", "score": 0.8}]
    _patch_crawl4ai(
        monkeypatch,
        adaptive_factory=make_fake_adaptive_crawler_factory(
            relevant=relevant, results=[about_result]
        ),
    )

    pages = asyncio.run(crawl_mod.select_pages("https://a.example"))

    assert pages["https://a.example/about"] == "FIT:<p>criteria</p>"
    assert "https://a.example/about" in calls
