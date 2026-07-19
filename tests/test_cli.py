"""Tests for the pescraper CLI.

Proves the command surface and exit-code contract via typer's CliRunner.
``doctor`` is NOT invoked here (its target module contacts real subsystems).
``_run_firm_async``'s pipeline orchestration is fully monkeypatched/offline per
RESEARCH.md's established "monkeypatch the target module's attribute directly"
convention (see ``test_crawl.py``, ``test_extract.py``) — no real network/
Ollama/disk state is touched by these tests.
"""

from __future__ import annotations

import asyncio

import pytest
from typer.testing import CliRunner

from pescraper import cli, confidence, crawl, db, extract, provenance
from pescraper.cli import app
from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria
from pescraper.models import FirmRecord, FirmStatus

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "run-firm", "export", "status", "doctor"):
        assert command in result.output
    # init-db is also registered
    assert "init-db" in result.output


def test_run_stub_exits_zero() -> None:
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0


def test_export_stub_exits_zero() -> None:
    result = runner.invoke(app, ["export"])
    assert result.exit_code == 0


def test_status_stub_exits_zero() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0


# --- _run_firm_async ---------------------------------------------------


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "pipeline.db"
    db.init_db(db_path)
    connection = db.connect(db_path)
    yield connection
    connection.close()


def test_run_firm_async_no_pages_skips_extraction_and_flags_needs_review(monkeypatch, conn) -> None:
    calls = {"financial": 0, "categorical": 0}

    async def fake_select_pages(url: str) -> dict[str, str]:
        return {}

    async def fake_extract_financial(pages, model="qwen3:4b"):
        calls["financial"] += 1
        raise AssertionError("extract_financial must not be called when no pages were selected")

    async def fake_extract_categorical(pages, model="qwen3:4b"):
        calls["categorical"] += 1
        raise AssertionError("extract_categorical must not be called when no pages were selected")

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages)
    monkeypatch.setattr(extract, "extract_financial", fake_extract_financial)
    monkeypatch.setattr(extract, "extract_categorical", fake_extract_categorical)

    record, provenance_rows = asyncio.run(cli._run_firm_async("https://noexample.com", conn))

    assert record.needs_review is True
    assert record.status == FirmStatus.NEEDS_REVIEW
    for field_name in confidence.POPULATABLE_FIELDS:
        if field_name == "website":
            continue
        assert getattr(record, field_name) is None
    assert provenance_rows == []
    assert calls == {"financial": 0, "categorical": 0}


def test_run_firm_async_populates_fields_and_provenance(monkeypatch, conn) -> None:
    url = "https://acme-capital.example"
    page_url = f"{url}/investment-criteria"
    pages = {page_url: "Acme Capital targets EBITDA of $5M to $25M. We focus on Buyouts."}

    async def fake_select_pages(_url: str) -> dict[str, str]:
        return pages

    async def fake_extract_financial(_pages, model="qwen3:4b"):
        return FinancialCriteria(
            firm_name="Acme Capital",
            ebitda_min_musd=5.0,
            ebitda_min_quote="EBITDA of $5M",
            ebitda_max_musd=25.0,
            ebitda_max_quote="to $25M",
        )

    async def fake_extract_categorical(_pages, model="qwen3:4b"):
        return CategoricalCriteria(
            firm_name="Acme Capital",
            deal_types="Buyout",
            deal_types_quote="We focus on Buyouts.",
        )

    found_quotes: list[str] = []

    def fake_find_source_page(quote, pages_arg, min_ratio=0.6):
        found_quotes.append(quote)
        return page_url

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages)
    monkeypatch.setattr(extract, "extract_financial", fake_extract_financial)
    monkeypatch.setattr(extract, "extract_categorical", fake_extract_categorical)
    monkeypatch.setattr(provenance, "find_source_page", fake_find_source_page)

    record, provenance_rows = asyncio.run(cli._run_firm_async(url, conn))

    assert record.ebitda_min_musd == 5.0
    assert record.ebitda_max_musd == 25.0
    assert record.deal_types == "Buyout"
    assert record.firm_name == "Acme Capital"

    fields_written = {row["field"] for row in provenance_rows}
    assert fields_written == {"ebitda_min_musd", "ebitda_max_musd", "deal_types"}
    for row in provenance_rows:
        assert row["source_page_url"] == page_url
        assert row["content_hash"]
    assert set(found_quotes) == {"EBITDA of $5M", "to $25M", "We focus on Buyouts."}


def test_run_firm_async_preserves_existing_confirmed_value_on_null_extraction(monkeypatch, conn) -> None:
    url = "https://beta-partners.example"
    existing = FirmRecord(
        firm_name="Beta Partners",
        website=url,
        ebitda_min_musd=10.0,
        ebitda_max_musd=20.0,
        confidence=0.9,
        needs_review=False,
        status=FirmStatus.COMPLETE,
    )
    db.upsert_firm(conn, existing)

    pages = {f"{url}/approach": "Beta Partners invests in enterprise value $50M-$150M deals."}

    async def fake_select_pages(_url: str) -> dict[str, str]:
        return pages

    async def fake_extract_financial(_pages, model="qwen3:4b"):
        # ebitda is silent on this run; ev is populated so confidence/core-numerics
        # both clear on the fresh run alone, per this task's own confidence logic.
        return FinancialCriteria(
            firm_name="Beta Partners",
            ebitda_min_musd=None,
            ev_min_musd=50.0,
            ev_min_quote="enterprise value $50M",
            ev_max_musd=150.0,
            ev_max_quote="$150M",
        )

    async def fake_extract_categorical(_pages, model="qwen3:4b"):
        return CategoricalCriteria(
            firm_name="Beta Partners",
            type="Private Equity",
            state="NY",
            city="New York",
            deal_types="Buyout",
            sector_tier1="Technology",
            activity="Active",
        )

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages)
    monkeypatch.setattr(extract, "extract_financial", fake_extract_financial)
    monkeypatch.setattr(extract, "extract_categorical", fake_extract_categorical)
    monkeypatch.setattr(provenance, "find_source_page", lambda quote, pages_arg, min_ratio=0.6: next(iter(pages)))

    record, _provenance_rows = asyncio.run(cli._run_firm_async(url, conn))

    assert record.ebitda_min_musd == 10.0  # null never overwrites a confirmed value
    assert record.ebitda_max_musd == 20.0
    assert record.ev_min_musd == 50.0  # fresh non-null value wins
    assert record.needs_review is False
    assert record.status == FirmStatus.COMPLETE


def test_run_firm_async_range_conflict_forces_needs_review(monkeypatch, conn) -> None:
    url = "https://gamma-equity.example"
    existing = FirmRecord(
        firm_name="Gamma Equity",
        website=url,
        ebitda_min_musd=10.0,
        ebitda_max_musd=20.0,
        confidence=0.9,
        needs_review=False,
        status=FirmStatus.COMPLETE,
    )
    db.upsert_firm(conn, existing)

    pages = {f"{url}/criteria": "Gamma Equity targets EBITDA of $30M to $40M."}

    async def fake_select_pages(_url: str) -> dict[str, str]:
        return pages

    async def fake_extract_financial(_pages, model="qwen3:4b"):
        # Disjoint from the existing confirmed 10-20 range -> a real conflict.
        return FinancialCriteria(
            firm_name="Gamma Equity",
            ebitda_min_musd=30.0,
            ebitda_min_quote="EBITDA of $30M",
            ebitda_max_musd=40.0,
            ebitda_max_quote="to $40M",
        )

    async def fake_extract_categorical(_pages, model="qwen3:4b"):
        return CategoricalCriteria(
            firm_name="Gamma Equity",
            type="Private Equity",
            state="CA",
            city="San Francisco",
            deal_types="Buyout",
            sector_tier1="Healthcare",
            activity="Active",
        )

    monkeypatch.setattr(crawl, "select_pages", fake_select_pages)
    monkeypatch.setattr(extract, "extract_financial", fake_extract_financial)
    monkeypatch.setattr(extract, "extract_categorical", fake_extract_categorical)
    monkeypatch.setattr(provenance, "find_source_page", lambda quote, pages_arg, min_ratio=0.6: next(iter(pages)))

    record, _provenance_rows = asyncio.run(cli._run_firm_async(url, conn))

    assert record.needs_review is True
    assert record.status == FirmStatus.NEEDS_REVIEW


# --- run-firm CLI command ------------------------------------------------


class _FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_run_firm_wires_pipeline_and_prints_summary(monkeypatch) -> None:
    url = "https://example.com"
    record = FirmRecord(
        firm_name="Acme Capital",
        website=url,
        confidence=0.75,
        needs_review=False,
        status=FirmStatus.COMPLETE,
    )
    provenance_rows = [
        {
            "field": "ebitda_min_musd",
            "value": "5.0",
            "quote": "EBITDA of $5M+",
            "source_page_url": f"{url}/criteria",
            "content_hash": "abc123",
            "prompt_version": "financial_v1",
        }
    ]

    async def fake_run_firm_async(_url: str, _conn) -> tuple[FirmRecord, list[dict]]:
        return record, provenance_rows

    fake_conn = _FakeConn()
    upserted: list[tuple[object, FirmRecord]] = []
    inserted: list[dict] = []

    monkeypatch.setattr(cli, "_run_firm_async", fake_run_firm_async)
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "connect", lambda: fake_conn)
    monkeypatch.setattr(db, "upsert_firm", lambda c, r: upserted.append((c, r)))
    monkeypatch.setattr(db, "insert_extraction", lambda c, **kwargs: inserted.append(kwargs))

    result = runner.invoke(app, ["run-firm", url])

    assert result.exit_code == 0
    assert upserted == [(fake_conn, record)]
    assert len(inserted) == 1
    assert inserted[0]["field"] == "ebitda_min_musd"
    assert fake_conn.closed is True
    assert "Acme Capital" in result.output
    assert "status=complete" in result.output
    assert "confidence=0.75" in result.output
    assert "needs_review=False" in result.output
    assert "extractions_written=1" in result.output
