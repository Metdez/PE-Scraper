from __future__ import annotations

import asyncio

from pescraper import cache, cli, crawl, db, extract
from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria
from pescraper.models import FirmRecord, FirmStatus


def test_put_and_get_cached_round_trip(tmp_path) -> None:
    conn = db.connect(db.init_db(tmp_path / "pipeline.db"))
    cache.put_cached(
        conn, kind="financial", model="qwen3:4b", prompt_version="v1",
        content_hash="abc123", value='{"firm_name": "Acme"}',
        source_text="x" * 100,
    )
    got = cache.get_cached(conn, kind="financial", model="qwen3:4b", prompt_version="v1", content_hash="abc123")
    assert got == '{"firm_name": "Acme"}'
    conn.close()


def test_put_cached_skips_near_empty_content(tmp_path) -> None:
    conn = db.connect(db.init_db(tmp_path / "pipeline.db"))
    cache.put_cached(
        conn, kind="financial", model="qwen3:4b", prompt_version="v1",
        content_hash="abc123", value='{}', source_text="short",
    )
    assert cache.get_cached(conn, kind="financial", model="qwen3:4b", prompt_version="v1", content_hash="abc123") is None
    conn.close()


def test_invalidate_stale_prompt_versions(tmp_path) -> None:
    conn = db.connect(db.init_db(tmp_path / "pipeline.db"))
    cache.put_cached(conn, kind="financial", model="m", prompt_version="v1", content_hash="h", value="v", source_text="x" * 100)
    cache.put_cached(conn, kind="financial", model="m", prompt_version="v2", content_hash="h", value="v", source_text="x" * 100)
    deleted = cache.invalidate_stale_prompt_versions(conn, "v2")
    assert deleted == 1
    assert cache.get_cached(conn, kind="financial", model="m", prompt_version="v1", content_hash="h") is None
    assert cache.get_cached(conn, kind="financial", model="m", prompt_version="v2", content_hash="h") == "v"
    conn.close()


def test_extraction_memoization_skips_second_ollama_call(monkeypatch, tmp_path) -> None:
    conn = db.connect(db.init_db(tmp_path / "pipeline.db"))
    call_count = {"n": 0}

    def fake_extract(pages, firm_name, model=extract.DEFAULT_MODEL):
        call_count["n"] += 1
        return (
            FinancialCriteria(firm_name=firm_name, ebitda_min_musd=5.0),
            CategoricalCriteria(firm_name=firm_name, type="PE"),
        )

    monkeypatch.setattr(extract, "extract", fake_extract)
    pages = {"https://a.example": "x" * 200}

    cli._cached_extract(conn, pages, "Acme")
    cli._cached_extract(conn, pages, "Acme")

    assert call_count["n"] == 1  # second call served from cache
    conn.close()


def test_same_day_rerun_skips_recrawl(monkeypatch, tmp_path) -> None:
    from datetime import datetime, timezone

    db_path = tmp_path / "pipeline.db"
    conn = db.connect(db.init_db(db_path))
    db.upsert_firm(
        conn,
        FirmRecord(
            firm_name="Acme",
            website="https://acme.example",
            status=FirmStatus.COMPLETE,
            confidence=0.9,
            last_checked=datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.close()

    calls = {"n": 0}

    async def fake_select_pages(url: str):
        calls["n"] += 1
        return {}

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages)
    monkeypatch.setattr(db, "init_db", lambda *a, **k: db_path)

    result = asyncio.run(cli.run_firm_pipeline("https://acme.example"))

    assert calls["n"] == 0  # crawl never invoked — cache-skip fired
    assert result.confidence == 0.9
