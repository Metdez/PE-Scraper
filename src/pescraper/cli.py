"""pescraper command-line interface.

The command surface (run, run-firm, export, status, doctor, init-db) is the
stable seam that later phases and the Windows Task Scheduler / nanoclaw
orchestration invoke.

Phase 2 replaces ``run-firm``'s Phase 1 stub with the real single-firm
pipeline: page selection -> decongestion -> qwen3:4b structured extraction ->
code-computed confidence -> null-safe merge -> persistence. ``run``, ``export``,
and ``status`` remain Phase 1 stubs; the batch/queue worker and export/report
paths land in later phases.

Importing this module imports ``pescraper``, which activates the Windows runtime
hardening (Proactor policy + UTF-8) as a side effect, so the console entry point
runs under the hardened runtime.

Heavier implementation modules (``pescraper.doctor``, ``pescraper.db``,
``pescraper.crawl``, ``pescraper.extract``, ``pescraper.confidence``,
``pescraper.merge``, ``pescraper.provenance``, ``pescraper.decongest``,
``pescraper.models``) are deliberately imported *lazily inside function bodies*
so ``pescraper --help`` and every not-yet-exercised command stay fast, and so
tests can monkeypatch each target module's attributes directly (the lazy
``from pescraper import X`` picks up the same module object a test's
``monkeypatch.setattr(X, "name", fake)`` mutates — the same pattern
``test_doctor.py`` already uses for ``ollama.chat``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    import sqlite3

    from pescraper.models import FirmRecord

app = typer.Typer(
    help="PE Scraper — build and maintain a dataset of US private equity firms' investment criteria.",
    no_args_is_help=True,
)

logger = logging.getLogger(__name__)

# Maps each *_quote field on FinancialCriteria/CategoricalCriteria to the value
# field it supports. Not a simple string-suffix transform (e.g. "rev_min_quote"
# supports "rev_min_musd", not "rev_min_musd_quote"), so an explicit table is
# the clearest, least-surprising representation of this fixed contract.
_FINANCIAL_QUOTE_TO_VALUE: dict[str, str] = {
    "rev_min_quote": "rev_min_musd",
    "rev_max_quote": "rev_max_musd",
    "ebitda_min_quote": "ebitda_min_musd",
    "ebitda_max_quote": "ebitda_max_musd",
    "ev_min_quote": "ev_min_musd",
    "ev_max_quote": "ev_max_musd",
    "check_min_quote": "check_min_musd",
    "check_max_quote": "check_max_musd",
    "aum_quote": "aum_musd",
}
_CATEGORICAL_QUOTE_TO_VALUE: dict[str, str] = {
    "deal_types_quote": "deal_types",
    "sector_tier1_quote": "sector_tier1",
}


def _derive_firm_name(url: str) -> str:
    """Fall back to a URL-derived firm name when extraction found nothing to report."""
    from urllib.parse import urlparse

    netloc = urlparse(url).netloc or url
    return netloc[4:] if netloc.startswith("www.") else netloc


async def _run_firm_async(url: str, conn: "sqlite3.Connection") -> "tuple[FirmRecord, list[dict]]":
    """Run the full single-firm pipeline: crawl -> extract -> score -> merge.

    Returns the record to persist (already null-safe-merged against any
    existing row for ``url``) and the list of provenance-row dicts to write to
    ``extractions`` (one per extracted field with a non-empty quote).

    Never calls ``db.advance_status``: that function validates transitions
    against the queue-claim lifecycle (``ALLOWED_TRANSITIONS``) that Phase 4's
    batch worker owns. An ad-hoc ``run-firm <url>`` on a firm not yet in the
    queue has no ``pending`` row to transition from, so calling it here would
    raise ``ValueError`` on a firm's first-ever run. ``run_firm`` (below) writes
    the already-terminal status directly via ``db.upsert_firm``, which is
    correct for this single-shot ad-hoc path.
    """
    from datetime import datetime, timezone

    from pescraper import cache, confidence, crawl, db, decongest, merge, models, provenance

    pages = cache.get_cached_pages(conn, url)
    if pages is None:
        pages = await crawl.select_pages(url)
        if pages:
            cache.put_cached_pages(conn, url, pages)

    if not pages:
        logger.warning("needs_review: no_criteria_page (%s)", url)
        record = models.FirmRecord(
            firm_name=_derive_firm_name(url),
            website=url,
            needs_review=True,
            status=models.FirmStatus.NEEDS_REVIEW,
        )
        return record, []

    financial, categorical = await cache.extract_cached(conn, pages)

    provenance_rows: list[dict] = []
    quote_sources = (
        (financial, _FINANCIAL_QUOTE_TO_VALUE, "financial_v1"),
        (categorical, _CATEGORICAL_QUOTE_TO_VALUE, "categorical_v1"),
    )
    for source, quote_map, prompt_version in quote_sources:
        for quote_field, value_field in quote_map.items():
            value = getattr(source, value_field, None)
            if value is None:
                continue
            quote_value = getattr(source, quote_field, None)
            source_page_url = (
                provenance.find_source_page(quote_value, pages) if quote_value else None
            )
            provenance_rows.append(
                {
                    "field": value_field,
                    "value": str(value) if value is not None else None,
                    "quote": quote_value,
                    "source_page_url": source_page_url,
                    "content_hash": (
                        decongest.content_hash(pages[source_page_url]) if source_page_url else None
                    ),
                    "prompt_version": prompt_version,
                }
            )

    firm_name = (categorical.firm_name or "").strip() or (financial.firm_name or "").strip()
    if not firm_name:
        firm_name = _derive_firm_name(url)

    fresh_record = models.FirmRecord(
        firm_name=firm_name,
        website=url,
        type=categorical.type,
        state=categorical.state,
        city=categorical.city,
        us_investments=categorical.us_investments,
        rev_min_musd=financial.rev_min_musd,
        rev_max_musd=financial.rev_max_musd,
        ebitda_min_musd=financial.ebitda_min_musd,
        ebitda_max_musd=financial.ebitda_max_musd,
        ev_min_musd=financial.ev_min_musd,
        ev_max_musd=financial.ev_max_musd,
        check_min_musd=financial.check_min_musd,
        check_max_musd=financial.check_max_musd,
        deal_types=categorical.deal_types,
        sector_tier1=categorical.sector_tier1,
        aum_musd=financial.aum_musd,
        activity=categorical.activity,
        last_deal=categorical.last_deal,
        fund_name=categorical.fund_name,
    )

    conf = confidence.compute_confidence(fresh_record)
    needs_review = confidence.is_needs_review(fresh_record, conf)
    fresh_record.confidence = conf
    fresh_record.needs_review = needs_review
    fresh_record.last_checked = datetime.now(timezone.utc).isoformat()

    existing = db.get_firm(conn, url)
    merged, conflicts = merge.merge_firm_record(existing, fresh_record)

    # merge.merge_firm_record copies lifecycle fields (status/confidence/
    # needs_review/last_checked) unchanged from `existing` by design (see its
    # module docstring) — this caller explicitly decides them from the fresh
    # run's own confidence/conflict logic, per CONTEXT.md.
    merged.confidence = conf
    merged.needs_review = needs_review
    merged.last_checked = fresh_record.last_checked

    if conflicts:
        merged.needs_review = True
        logger.warning("needs_review: seed_conflict:%s (%s)", conflicts, url)
    elif merged.needs_review:
        reason = "low_confidence" if conf < confidence.NEEDS_REVIEW_THRESHOLD else "zero_core_numerics"
        logger.warning("needs_review: %s (%s)", reason, url)

    merged.status = models.FirmStatus.NEEDS_REVIEW if merged.needs_review else models.FirmStatus.COMPLETE

    return merged, provenance_rows


def _write_provenance(conn: "sqlite3.Connection", url: str, rows: list[dict]) -> None:
    from pescraper import db

    for row in rows:
        db.insert_extraction(
            conn,
            firm_website=url,
            field=row["field"],
            value=row["value"],
            quote=row["quote"],
            source_page_url=row["source_page_url"],
            model="qwen3:4b",
            prompt_version=row["prompt_version"],
            content_hash=row["content_hash"],
        )


@app.command()
def run(
    slug: str | None = typer.Option(None, help="Queue one firm URL at urgent priority."),
    limit: int | None = typer.Option(None, min=1, help="Maximum firms to process."),
    summary: bool = typer.Option(False, help="Show queue counts without processing."),
    csv_path: Path | None = typer.Option(None, "--csv", exists=True, help="Seed firms from CSV."),
) -> None:
    """Run queued firms with per-firm commits and failure isolation."""
    import asyncio

    from pescraper import db, ingest, queue, worker

    db.init_db()
    conn = db.connect()
    try:
        if csv_path:
            ingest.ingest_csv(csv_path, conn)
            for row in conn.execute("SELECT website FROM firms WHERE website IS NOT NULL"):
                queue.enqueue(conn, row["website"])
        if slug:
            queue.enqueue(conn, slug, priority=0)
        if summary:
            typer.echo(json.dumps(queue.queue_summary(conn), sort_keys=True))
            return

        def processor(url: str) -> "FirmRecord":
            record, provenance_rows = asyncio.run(_run_firm_async(url, conn))
            _write_provenance(conn, url, provenance_rows)
            return record

        result = worker.run_batch(conn, processor, limit=limit)
        typer.echo(f"completed={result.completed} failed={result.failed}")
    finally:
        conn.close()


@app.command("run-firm")
def run_firm(url: str = typer.Argument(..., help="Firm website URL to research.")) -> None:
    """Research a single firm by URL: crawl, extract, score, and persist."""
    import asyncio

    from pescraper import db

    db.init_db()
    conn = db.connect()
    try:
        record, provenance_rows = asyncio.run(_run_firm_async(url, conn))
        db.upsert_firm(conn, record)
        _write_provenance(conn, url, provenance_rows)
    finally:
        conn.close()

    typer.echo(
        f"{record.firm_name}: status={record.status.value} "
        f"confidence={(record.confidence or 0.0):.2f} "
        f"needs_review={record.needs_review} "
        f"extractions_written={len(provenance_rows)}"
    )


@app.command()
def export(output: Path = typer.Option(Path("data/exports/firms"), help="Output path without suffix.")) -> None:
    """Export the dataset to styled Excel and UTF-8 CSV."""
    from pescraper import db
    from pescraper.exporter import export_dataset

    db.init_db()
    conn = db.connect()
    try:
        csv_path, xlsx_path = export_dataset(conn, output)
    finally:
        conn.close()
    typer.echo(f"csv={csv_path} xlsx={xlsx_path}")


@app.command()
def status() -> None:
    """Show queue and firm lifecycle counts."""
    from pescraper import db
    from pescraper.queue import queue_summary

    db.init_db()
    conn = db.connect()
    try:
        firms = {
            row["status"]: row["count"]
            for row in conn.execute("SELECT status, COUNT(*) count FROM firms GROUP BY status")
        }
        payload = {"jobs": queue_summary(conn), "firms": firms}
    finally:
        conn.close()
    typer.echo(json.dumps(payload, sort_keys=True))


@app.command()
def benchmark(fixture: Path = typer.Argument(..., exists=True)) -> None:
    """Score a hand-verified JSONL fixture and print per-field accuracy."""
    from pescraper.benchmark import evaluate_cases, load_cases

    report = evaluate_cases(load_cases(fixture))
    typer.echo(json.dumps(report.as_dict(), indent=2, sort_keys=True))


@app.command()
def heartbeat(limit: int | None = typer.Option(None, min=1)) -> None:
    """Process queued and stale firms; exit before model work when idle."""
    import asyncio

    from pescraper import automation, db

    db.init_db()
    conn = db.connect()
    try:
        def processor(url: str) -> "FirmRecord":
            record, provenance_rows = asyncio.run(_run_firm_async(url, conn))
            _write_provenance(conn, url, provenance_rows)
            return record

        result = automation.heartbeat(conn, processor, limit=limit)
    finally:
        conn.close()
    typer.echo(
        json.dumps(
            {"completed": result.completed, "failed": result.failed, "skipped": result.skipped}
        )
    )


@app.command("research")
def research_firm(name_or_url: str) -> None:
    """Print one stored firm's complete criteria record."""
    from pescraper import db
    from pescraper.dataset import find_firm, format_firm

    db.init_db()
    conn = db.connect()
    try:
        record = find_firm(conn, name_or_url)
    finally:
        conn.close()
    if record is None:
        raise typer.BadParameter(f"Firm not found: {name_or_url}")
    typer.echo(format_firm(record))


@app.command("ask")
def ask_dataset(
    ebitda_min: float | None = typer.Option(None),
    ebitda_max: float | None = typer.Option(None),
    deal_type: str | None = typer.Option(None),
    sector: str | None = typer.Option(None),
) -> None:
    """Query firms by structured investment criteria."""
    from pescraper import db
    from pescraper.dataset import search_firms

    db.init_db()
    conn = db.connect()
    try:
        records = search_firms(
            conn,
            ebitda_min=ebitda_min,
            ebitda_max=ebitda_max,
            deal_type=deal_type,
            sector=sector,
        )
    finally:
        conn.close()
    for record in records:
        typer.echo(f"{record.firm_name}\t{record.website}")


@app.command("discover")
def discover(
    query: str = typer.Option("US private equity firm investment criteria"),
    searx_url: str = typer.Option("http://localhost:8080"),
) -> None:
    """Discover and queue new PE firms through a SearXNG JSON endpoint."""
    from pescraper import db
    from pescraper.discovery import SearxClient, discover_firms

    results = SearxClient(searx_url).search(query)
    db.init_db()
    conn = db.connect()
    try:
        firms = discover_firms(conn, results)
    finally:
        conn.close()
    typer.echo(f"discovered={len(firms)}")


@app.command()
def doctor() -> None:
    """Run the Windows environment smoke test (Proactor, Ollama, Crawl4AI)."""
    # Lazy import: pescraper.doctor lands in wave 2. Keeping this inside the
    # function body means --help and the other commands work before it exists.
    from pescraper.doctor import main

    raise typer.Exit(code=main())


@app.command("init-db")
def init_db() -> None:
    """Initialize pipeline.db (schema + WAL) at its configured path."""
    # Lazy import: pescraper.db lands in wave 2.
    from pescraper.db import init_db as _init_db

    db_path = _init_db()
    typer.echo(f"Initialized pipeline database at: {db_path}")


if __name__ == "__main__":
    app()
