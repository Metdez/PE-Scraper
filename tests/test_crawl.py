"""Offline tests for pescraper.crawl.select_pages.

AsyncWebCrawler/AdaptiveCrawler are fully mocked (RESEARCH.md's "monkeypatch to lock
contract shape" pattern) — no real browser or network is touched. Tests run the async
select_pages() via asyncio.run() inside plain ``def test_...()`` functions, matching
the plan's "no pytest-asyncio dependency needed" instruction.
"""

from __future__ import annotations

import asyncio

from pescraper import crawl


class FakeResult:
    def __init__(self, url: str, cleaned_html: str = "", success: bool = True) -> None:
        self.url = url
        self.cleaned_html = cleaned_html
        self.success = success


class FakeState:
    def __init__(self, knowledge_base: list[FakeResult]) -> None:
        self.knowledge_base = knowledge_base


class FakeAdaptiveCrawler:
    """Stands in for crawl4ai.adaptive_crawler.AdaptiveCrawler."""

    def __init__(
        self,
        crawler,
        config=None,
        digest_result: FakeState | None = None,
        digest_exc: Exception | None = None,
        relevant: list[dict] | None = None,
    ) -> None:
        self._crawler = crawler
        self.config = config
        self._digest_result = digest_result
        self._digest_exc = digest_exc
        self._relevant = relevant or []

    async def digest(self, start_url: str, query: str) -> FakeState:
        if self._digest_exc is not None:
            raise self._digest_exc
        return self._digest_result

    def get_relevant_content(self, top_k: int = 5) -> list[dict]:
        return self._relevant


class FakeAsyncWebCrawler:
    """Stands in for crawl4ai.AsyncWebCrawler as an async context manager."""

    def __init__(
        self,
        arun_results: dict[str, FakeResult] | None = None,
        arun_exc: Exception | None = None,
    ) -> None:
        self.arun_results = arun_results or {}
        self.arun_exc = arun_exc
        self.arun_calls: list[str] = []

    async def __aenter__(self) -> "FakeAsyncWebCrawler":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def arun(self, url: str, config=None) -> FakeResult:
        self.arun_calls.append(url)
        if self.arun_exc is not None:
            raise self.arun_exc
        return self.arun_results.get(url, FakeResult(url, cleaned_html="", success=False))


def _wire(
    monkeypatch,
    *,
    digest_result: FakeState | None = None,
    digest_exc: Exception | None = None,
    relevant: list[dict] | None = None,
    arun_results: dict[str, FakeResult] | None = None,
    arun_exc: Exception | None = None,
) -> FakeAsyncWebCrawler:
    fake_web = FakeAsyncWebCrawler(arun_results=arun_results, arun_exc=arun_exc)

    def fake_async_web_crawler_factory(*args, **kwargs) -> FakeAsyncWebCrawler:
        return fake_web

    def fake_adaptive_crawler_factory(crawler, config=None) -> FakeAdaptiveCrawler:
        return FakeAdaptiveCrawler(
            crawler,
            config=config,
            digest_result=digest_result,
            digest_exc=digest_exc,
            relevant=relevant,
        )

    monkeypatch.setattr(crawl, "AsyncWebCrawler", fake_async_web_crawler_factory)
    monkeypatch.setattr(crawl, "AdaptiveCrawler", fake_adaptive_crawler_factory)

    # Marker decongest: proves select_pages routes content through decongest.decongest
    # rather than returning raw markdown, per PIPE-02's contract.
    def fake_decongest(cleaned_html: str, base_url: str) -> str:
        return f"FIT::{cleaned_html}" if cleaned_html else ""

    monkeypatch.setattr(crawl.decongest, "decongest", fake_decongest)

    return fake_web


def test_select_pages_excludes_skip_listed_urls(monkeypatch) -> None:
    kb = [
        FakeResult("https://a.example/team", cleaned_html="<html>team</html>"),
        FakeResult("https://a.example/about", cleaned_html="<html>about</html>"),
    ]
    relevant = [
        {"url": "https://a.example/team", "score": 0.9, "content": "raw", "index": 0},
        {"url": "https://a.example/about", "score": 0.8, "content": "raw", "index": 1},
    ]
    _wire(monkeypatch, digest_result=FakeState(kb), relevant=relevant)

    result = asyncio.run(crawl.select_pages("https://a.example"))

    assert "https://a.example/team" not in result
    assert result == {"https://a.example/about": "FIT::<html>about</html>"}


def test_select_pages_falls_back_to_well_known_paths(monkeypatch) -> None:
    # Zero relevant results triggers the well-known-path fallback.
    arun_results = {
        "https://a.example/about": FakeResult(
            "https://a.example/about", cleaned_html="<html>about-fallback</html>", success=True
        ),
        "https://a.example/strategy": FakeResult(
            "https://a.example/strategy", cleaned_html="", success=False
        ),
    }
    fake_web = _wire(
        monkeypatch,
        digest_result=FakeState([]),
        relevant=[],
        arun_results=arun_results,
    )

    result = asyncio.run(crawl.select_pages("https://a.example"))

    assert result == {"https://a.example/about": "FIT::<html>about-fallback</html>"}
    # All four well-known paths were attempted.
    assert set(fake_web.arun_calls) == {
        "https://a.example" + p for p in crawl.WELL_KNOWN_PATHS
    }


def test_select_pages_total_failure_returns_empty_dict_without_raising(monkeypatch) -> None:
    _wire(
        monkeypatch,
        digest_exc=RuntimeError("blocked (403)"),
        relevant=[],
        arun_exc=RuntimeError("blocked (403) on fallback too"),
    )

    result = asyncio.run(crawl.select_pages("https://a.example"))

    assert result == {}


def test_select_pages_content_is_always_decongested(monkeypatch) -> None:
    kb = [FakeResult("https://a.example/approach", cleaned_html="<html>approach</html>")]
    relevant = [{"url": "https://a.example/approach", "score": 0.5, "content": "raw", "index": 0}]
    _wire(monkeypatch, digest_result=FakeState(kb), relevant=relevant)

    result = asyncio.run(crawl.select_pages("https://a.example"))

    assert result["https://a.example/approach"].startswith("FIT::")
    assert "raw" not in result["https://a.example/approach"]
