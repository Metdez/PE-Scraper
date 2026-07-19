from __future__ import annotations

import asyncio

from pescraper import db, extract
from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria


def _conn(tmp_path):
    path = tmp_path / "pipeline.db"
    db.init_db(path)
    return db.connect(path)


def test_cache_key_invalidates_on_prompt_version(tmp_path) -> None:
    from pescraper.cache import get_cached, put_cached

    conn = _conn(tmp_path)
    put_cached(conn, "financial", "hash1", "financial_v1", "qwen3:4b", {"value": 5})

    assert get_cached(conn, "financial", "hash1", "financial_v1", "qwen3:4b") == {"value": 5}
    assert get_cached(conn, "financial", "hash1", "financial_v2", "qwen3:4b") is None


def test_extract_cached_reuses_identical_content(monkeypatch, tmp_path) -> None:
    from pescraper.cache import extract_cached

    conn = _conn(tmp_path)
    calls = {"financial": 0, "categorical": 0}

    async def financial(pages, model="qwen3:4b"):
        calls["financial"] += 1
        return FinancialCriteria(firm_name="Acme", ebitda_min_musd=5)

    async def categorical(pages, model="qwen3:4b"):
        calls["categorical"] += 1
        return CategoricalCriteria(firm_name="Acme", deal_types="Buyout")

    monkeypatch.setattr(extract, "extract_financial", financial)
    monkeypatch.setattr(extract, "extract_categorical", categorical)
    pages = {"https://acme.example/criteria": "Acme targets EBITDA of $5M."}

    first = asyncio.run(extract_cached(conn, pages))
    second = asyncio.run(extract_cached(conn, pages))

    assert first == second
    assert calls == {"financial": 1, "categorical": 1}


def test_blocked_shell_content_is_not_cached(monkeypatch, tmp_path) -> None:
    from pescraper.cache import extract_cached

    conn = _conn(tmp_path)
    calls = 0

    async def financial(pages, model="qwen3:4b"):
        nonlocal calls
        calls += 1
        return FinancialCriteria(firm_name="Blocked")

    async def categorical(pages, model="qwen3:4b"):
        return CategoricalCriteria(firm_name="Blocked")

    monkeypatch.setattr(extract, "extract_financial", financial)
    monkeypatch.setattr(extract, "extract_categorical", categorical)
    pages = {"https://blocked.example": "Access denied. Enable JavaScript to continue."}

    asyncio.run(extract_cached(conn, pages))
    asyncio.run(extract_cached(conn, pages))

    assert calls == 2


def test_page_cache_reuses_fresh_pages_and_rejects_poison(tmp_path) -> None:
    from pescraper.cache import get_cached_pages, put_cached_pages

    conn = _conn(tmp_path)
    pages = {"https://acme.example/criteria": "Acme targets EBITDA of $5M."}

    assert put_cached_pages(conn, "https://acme.example", pages) is True
    assert get_cached_pages(conn, "https://acme.example") == pages

    poisoned = {"https://blocked.example": "Access denied. Enable JavaScript to continue."}
    assert put_cached_pages(conn, "https://blocked.example", poisoned) is False
    assert get_cached_pages(conn, "https://blocked.example") is None
