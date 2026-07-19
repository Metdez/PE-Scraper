"""Offline tests for cli.run_firm_pipeline — the Phase 2 integration seam.

Mocks crawl.select_pages and extract.extract (both already covered by their own
offline test suites) and points the pipeline at a tmp_path SQLite database, so
this file proves the *orchestration* (merge, confidence, provenance, persistence)
without touching real network/Ollama/Chromium.
"""

from __future__ import annotations

import asyncio
from functools import partial

from pescraper import cli, crawl, db, extract
from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria
from pescraper.models import FirmStatus


def _use_tmp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "pipeline.db"
    monkeypatch.setattr(db, "init_db", partial(db.init_db, db_path))
    return db_path


def test_no_pages_found_flags_needs_review_zero_confidence(monkeypatch, tmp_path) -> None:
    _use_tmp_db(monkeypatch, tmp_path)

    async def fake_select_pages(url: str) -> dict[str, str]:
        return {}

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages)

    record = asyncio.run(cli.run_firm_pipeline("https://blocked.example"))

    assert record.needs_review is True
    assert record.status == FirmStatus.NEEDS_REVIEW
    # website is the only populated field for a brand-new blocked firm — near-zero.
    assert record.confidence < 0.1


def test_happy_path_persists_scores_and_records_provenance(monkeypatch, tmp_path) -> None:
    db_path = _use_tmp_db(monkeypatch, tmp_path)
    url = "https://acme.example"
    quote = "EBITDA of $5 million to $25 million for control buyouts"
    page_text = f"Our investment criteria: {quote}. We are an active PE firm."

    async def fake_select_pages(u: str) -> dict[str, str]:
        return {f"{url}/about": page_text}

    def fake_extract(pages, firm_name, model=extract.DEFAULT_MODEL):
        financial = FinancialCriteria(
            firm_name=firm_name,
            ebitda_min_musd=5.0,
            ebitda_min_quote=quote,
            ebitda_max_musd=25.0,
            ebitda_max_quote=quote,
        )
        categorical = CategoricalCriteria(
            firm_name=firm_name,
            type="PE",
            deal_types="Buyout",
            deal_types_quote=quote,
            activity="Active",
        )
        return financial, categorical

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages)
    monkeypatch.setattr(extract, "extract", fake_extract)

    record = asyncio.run(cli.run_firm_pipeline(url))

    assert record.ebitda_min_musd == 5.0
    assert record.ebitda_max_musd == 25.0
    assert record.deal_types == "Buyout"
    assert record.confidence > 0.0

    conn = db.connect(db_path)
    try:
        stored = db.get_firm(conn, url)
        assert stored == record

        rows = conn.execute(
            "SELECT * FROM extractions WHERE field = 'ebitda_min_musd'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["source_page_url"] == f"{url}/about"
        assert rows[0]["quote"] == quote
    finally:
        conn.close()


def test_rerun_with_blocked_crawl_preserves_prior_confirmed_values(monkeypatch, tmp_path) -> None:
    db_path = _use_tmp_db(monkeypatch, tmp_path)
    url = "https://acme.example"
    quote = "EBITDA of $5 million to $25 million"
    page_text = f"Criteria: {quote}."

    async def fake_select_pages_success(u: str) -> dict[str, str]:
        return {f"{url}/about": page_text}

    def fake_extract(pages, firm_name, model=extract.DEFAULT_MODEL):
        financial = FinancialCriteria(
            firm_name=firm_name, ebitda_min_musd=5.0, ebitda_min_quote=quote
        )
        categorical = CategoricalCriteria(firm_name=firm_name, type="PE")
        return financial, categorical

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages_success)
    monkeypatch.setattr(extract, "extract", fake_extract)
    first = asyncio.run(cli.run_firm_pipeline(url))
    assert first.ebitda_min_musd == 5.0

    # Backdate last_checked past the same-day cache-freshness window (CACH-01)
    # so the second call actually re-crawls instead of hitting the cache-skip —
    # simulating a 90-day staleness re-check, not a same-day rerun.
    conn = db.connect(db_path)
    conn.execute(
        "UPDATE firms SET last_checked = ? WHERE website = ?",
        ("2020-01-01T00:00:00+00:00", url),
    )
    conn.commit()
    conn.close()

    async def fake_select_pages_blocked(u: str) -> dict[str, str]:
        return {}

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages_blocked)
    second = asyncio.run(cli.run_firm_pipeline(url))

    # The transient crawl failure must not wipe the previously confirmed value.
    assert second.ebitda_min_musd == 5.0
    assert second.needs_review is True
    assert second.confidence > 0.0  # reflects preserved data, not slammed to 0

    conn = db.connect(db_path)
    try:
        stored = db.get_firm(conn, url)
        assert stored.ebitda_min_musd == 5.0
    finally:
        conn.close()
