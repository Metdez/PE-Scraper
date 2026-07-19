"""pescraper command-line interface.

The command surface (run, run-firm, export, status, doctor, init-db) is the
stable seam that later phases and the Windows Task Scheduler orchestration
invoke. ``run-firm`` is Phase 2's core deliverable: page selection -> HTML
decongestion -> qwen3:4b structured extraction -> merged 24-column row with
per-field provenance and code-computed confidence, persisted to pipeline.db.
``run``/``export``/``status`` remain stubs; batch/queue lands in Phase 4.

Importing this module imports ``pescraper``, which activates the Windows runtime
hardening (Proactor policy + UTF-8) as a side effect, so the console entry point
runs under the hardened runtime.

Heavier modules (``pescraper.doctor``/``db``/``crawl``/``extract``) are imported
*lazily inside function bodies* so ``pescraper --help`` stays fast.
"""

from __future__ import annotations

from typing import Optional

import typer

app = typer.Typer(
    help="PE Scraper — build and maintain a dataset of US private equity firms' investment criteria.",
    no_args_is_help=True,
)


@app.command()
def run(
    csv: Optional[str] = typer.Option(None, "--csv", help="Capital IQ CSV to seed the queue from."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max firms to process this run."),
    slug: Optional[str] = typer.Option(None, "--slug", help="Process exactly one firm by website URL."),
    summary: bool = typer.Option(False, "--summary", help="Print queue/firm status counts and exit."),
) -> None:
    """Run the crash-safe batch worker over queued firms (or one firm via --slug)."""
    import asyncio

    from pescraper import db, worker

    if summary:
        conn = db.connect(db.init_db())
        try:
            typer.echo(f"Firms by status: {db.firm_status_summary(conn)}")
            typer.echo(f"Jobs by status: {db.queue_summary(conn)}")
        finally:
            conn.close()
        return

    if csv:
        from pescraper.ingest import ingest_csv

        conn = db.connect(db.init_db())
        try:
            seeded = 0
            for record in ingest_csv(csv):
                if record.website and db.get_firm(conn, record.website) is not None:
                    continue
                db.upsert_firm(conn, record)
                seeded += 1
            typer.echo(f"Seeded {seeded} new firm(s) from {csv}")
        finally:
            conn.close()

    if slug:
        record = asyncio.run(run_firm_pipeline(slug))
        typer.echo(
            f"{record.firm_name} ({record.website}): status={record.status.value} "
            f"confidence={record.confidence:.2f} needs_review={record.needs_review}"
        )
        return

    result = asyncio.run(worker.run_batch(limit=limit))
    typer.echo(
        f"Processed {result.processed} firm(s): {result.succeeded} succeeded, "
        f"{result.failed} failed."
    )
    for website, error in result.failures:
        typer.echo(f"  FAILED {website}: {error}")


async def run_firm_pipeline(url: str):
    """Crawl -> decongest -> extract -> merge -> score -> persist one firm.

    Pure async core (no typer/CLI concerns) so it's directly testable. Does NOT
    consult Capital IQ seed data (CONTEXT.md: run-firm is the ad-hoc path, no
    CSV row exists for it). Returns the persisted FirmRecord.
    """
    import logging
    from datetime import datetime, timedelta, timezone

    from pescraper import crawl, db, decongest, extract, merge
    from pescraper.confidence import compute_confidence, is_needs_review
    from pescraper.models import FirmRecord, FirmStatus
    from pescraper.provenance import find_source_page

    logger = logging.getLogger(__name__)

    CACHE_FRESHNESS = timedelta(days=1)

    db_path = db.init_db()
    conn = db.connect(db_path)
    try:
        firm_name = _firm_name_from_url(url)
        existing = db.get_firm(conn, url)

        # CACH-01: an already-checked-today firm skips re-crawl and re-extraction
        # entirely — visibly faster, observable as a no-op in status counts.
        if (
            existing is not None
            and existing.last_checked
            and existing.status in (FirmStatus.COMPLETE, FirmStatus.NEEDS_REVIEW)
        ):
            checked_at = datetime.fromisoformat(existing.last_checked)
            if datetime.now(timezone.utc) - checked_at < CACHE_FRESHNESS:
                logger.info("cache: %s checked within %s, skipping re-crawl", url, CACHE_FRESHNESS)
                return existing

        if existing is None:
            db.upsert_firm(conn, FirmRecord(firm_name=firm_name, website=url))
        db.advance_status(conn, url, FirmStatus.IN_PROGRESS)

        pages = await crawl.select_pages(url)
        now_iso = datetime.now(timezone.utc).isoformat()

        if not pages:
            logger.warning("no_criteria_page: no relevant pages found for %s", url)
            candidate = FirmRecord(firm_name=firm_name, website=url)
            merged, _conflicts = merge.merge_firm_record(existing, candidate)
            # Null-safe merge means a prior successful run's values survive a
            # transient blocked/empty re-crawl — confidence reflects the real
            # (preserved) data, only needs_review/status flag this run's failure.
            confidence = compute_confidence(merged)
            merged = merged.model_copy(
                update={
                    "confidence": confidence,
                    "needs_review": True,
                    "status": FirmStatus.NEEDS_REVIEW,
                    "last_checked": now_iso,
                }
            )
            db.upsert_firm(conn, merged)
            return merged

        financial, categorical = _cached_extract(conn, pages, firm_name)

        candidate = FirmRecord(
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
        merged, conflicts = merge.merge_firm_record(existing, candidate)
        confidence = compute_confidence(merged)
        needs_review = is_needs_review(merged, confidence) or bool(conflicts)
        status = FirmStatus.NEEDS_REVIEW if needs_review else FirmStatus.COMPLETE
        merged = merged.model_copy(
            update={
                "confidence": confidence,
                "needs_review": needs_review,
                "status": status,
                "last_checked": now_iso,
            }
        )
        db.upsert_firm(conn, merged)

        quote_pairs = (
            ("rev_min_musd", financial.rev_min_musd, financial.rev_min_quote),
            ("rev_max_musd", financial.rev_max_musd, financial.rev_max_quote),
            ("ebitda_min_musd", financial.ebitda_min_musd, financial.ebitda_min_quote),
            ("ebitda_max_musd", financial.ebitda_max_musd, financial.ebitda_max_quote),
            ("ev_min_musd", financial.ev_min_musd, financial.ev_min_quote),
            ("ev_max_musd", financial.ev_max_musd, financial.ev_max_quote),
            ("check_min_musd", financial.check_min_musd, financial.check_min_quote),
            ("check_max_musd", financial.check_max_musd, financial.check_max_quote),
            ("aum_musd", financial.aum_musd, financial.aum_quote),
            ("deal_types", categorical.deal_types, categorical.deal_types_quote),
            ("sector_tier1", categorical.sector_tier1, categorical.sector_tier1_quote),
        )
        for field, value, quote in quote_pairs:
            if value is None:
                continue
            source_url = find_source_page(quote, pages)
            content_hash = decongest.content_hash(pages[source_url]) if source_url else None
            db.insert_extraction(
                conn,
                firm_website=url,
                field=field,
                value=str(value),
                quote=quote,
                source_page_url=source_url,
                model=extract.DEFAULT_MODEL,
                prompt_version=extract.PROMPT_VERSION,
                content_hash=content_hash,
            )

        return merged
    finally:
        conn.close()


def _cached_extract(conn, pages: dict[str, str], firm_name: str):
    """extract.extract(), memoized by (model, prompt_version, content_hash) —
    CACH-02: identical inputs are never re-spent. Bumping extract.PROMPT_VERSION
    naturally invalidates old entries (new cache key)."""
    from pescraper import cache, decongest, extract
    from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria

    assembled = extract.assemble_pages(pages)
    digest = decongest.content_hash(assembled)
    model = extract.DEFAULT_MODEL
    prompt_version = extract.PROMPT_VERSION

    cached_financial = cache.get_cached(
        conn, kind="financial", model=model, prompt_version=prompt_version, content_hash=digest
    )
    cached_categorical = cache.get_cached(
        conn, kind="categorical", model=model, prompt_version=prompt_version, content_hash=digest
    )
    if cached_financial is not None and cached_categorical is not None:
        return (
            FinancialCriteria.model_validate_json(cached_financial),
            CategoricalCriteria.model_validate_json(cached_categorical),
        )

    financial, categorical = extract.extract(pages, firm_name)
    cache.put_cached(
        conn, kind="financial", model=model, prompt_version=prompt_version,
        content_hash=digest, value=financial.model_dump_json(), source_text=assembled,
    )
    cache.put_cached(
        conn, kind="categorical", model=model, prompt_version=prompt_version,
        content_hash=digest, value=categorical.model_dump_json(), source_text=assembled,
    )
    return financial, categorical


def _firm_name_from_url(url: str) -> str:
    """Derive a placeholder firm name from a URL's hostname.

    Code-derived, never trusted from the model (per the project's "never trust
    the LLM for what code can determine" stance) — extraction only fills
    criteria fields, never the firm's identity.
    """
    from urllib.parse import urlparse

    host = urlparse(url).netloc or urlparse(url).path
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    stem = host.split(".")[0] if host else url
    return stem.replace("-", " ").title() or url


@app.command("run-firm")
def run_firm(url: str = typer.Argument(..., help="Firm website URL to research.")) -> None:
    """Research a single firm by URL: crawl, extract, merge, score, persist."""
    import asyncio

    record = asyncio.run(run_firm_pipeline(url))
    typer.echo(
        f"{record.firm_name} ({record.website}): status={record.status.value} "
        f"confidence={record.confidence:.2f} needs_review={record.needs_review}"
    )


@app.command()
def discover(
    query: list[str] = typer.Option(
        None, "--query", help="Search query (repeatable). Defaults to a small built-in set."
    ),
) -> None:
    """Find new US PE firms via web search, dedupe, and queue genuine new firms."""
    from pescraper import db, discovery

    queries = query or [
        "middle market private equity firm investment criteria site:.com",
        "growth equity firm investment criteria site:.com",
    ]
    conn = db.connect(db.init_db())
    try:
        queued = discovery.run_discovery(conn, queries)
    finally:
        conn.close()
    typer.echo(f"Queued {queued} newly discovered firm(s).")


@app.command("recover-urls")
def recover_urls() -> None:
    """Search for a working website for every firm with a missing URL."""
    from pescraper import db, discovery

    conn = db.connect(db.init_db())
    try:
        recovered = discovery.recover_dead_urls(conn)
    finally:
        conn.close()
    typer.echo(f"Recovered {recovered} firm website(s).")


@app.command()
def heartbeat(
    limit: int = typer.Option(50, "--limit", help="Max firms to process this heartbeat."),
) -> None:
    """Unattended entry point for Windows Task Scheduler: no-op if there's no
    queued or stale work (zero-cost idle sweep), otherwise runs the batch worker."""
    import asyncio

    from pescraper import worker

    result = asyncio.run(worker.run_heartbeat(limit=limit))
    if result.skipped:
        typer.echo(f"heartbeat: skipped ({result.reason})")
        return
    if result.batch is None:
        typer.echo(f"heartbeat: error ({result.reason})")
        raise typer.Exit(code=1)
    typer.echo(
        f"heartbeat: processed {result.batch.processed} firm(s) — "
        f"{result.batch.succeeded} succeeded, {result.batch.failed} failed"
    )


@app.command()
def find(
    state: Optional[str] = typer.Option(None, help="Exact state match, e.g. CT."),
    sector: Optional[str] = typer.Option(None, help="Sector substring match."),
    deal_type: Optional[str] = typer.Option(None, "--deal-type", help="Deal type substring match."),
    ebitda_min: Optional[float] = typer.Option(None, help="EBITDA range must overlap [min, max]."),
    ebitda_max: Optional[float] = typer.Option(None),
    rev_min: Optional[float] = typer.Option(None),
    rev_max: Optional[float] = typer.Option(None),
) -> None:
    """Filter the dataset — the CLI equivalent of a freeform "find firms that..." ask."""
    from pescraper import db
    from pescraper.query import find_firms

    conn = db.connect(db.init_db())
    try:
        records = db.all_firms(conn)
    finally:
        conn.close()

    matches = find_firms(
        records,
        state=state,
        sector=sector,
        deal_type=deal_type,
        ebitda_min=ebitda_min,
        ebitda_max=ebitda_max,
        rev_min=rev_min,
        rev_max=rev_max,
    )
    if not matches:
        typer.echo("No matching firms.")
        return
    for r in matches:
        typer.echo(
            f"{r.firm_name} | {r.state or '-'} | {r.sector_tier1 or '-'} | "
            f"{r.deal_types or '-'} | EBITDA {r.ebitda_min_musd}-{r.ebitda_max_musd} | "
            f"{r.website or '-'}"
        )


@app.command()
def benchmark() -> None:
    """Run the Phase 3 accuracy benchmark against the hand-verified golden set."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
    from benchmark.golden_set import GOLDEN_SET  # type: ignore[import-not-found]

    from pescraper.benchmark import format_report, run_benchmark

    report = run_benchmark(GOLDEN_SET)
    typer.echo(format_report(report))


@app.command()
def export(
    out: str = typer.Option("data/exports/firms", "--out", help="Output path, without extension."),
    fmt: str = typer.Option("both", "--format", help="csv, xlsx, or both."),
) -> None:
    """Export the firms dataset to Excel/CSV."""
    from pescraper import db, export as export_mod

    conn = db.connect(db.init_db())
    try:
        if fmt in ("csv", "both"):
            path = export_mod.export_csv(conn, f"{out}.csv")
            typer.echo(f"Wrote {path}")
        if fmt in ("xlsx", "both"):
            path = export_mod.export_excel(conn, f"{out}.xlsx")
            typer.echo(f"Wrote {path}")
    finally:
        conn.close()


@app.command()
def status() -> None:
    """Show pipeline/queue status."""
    from pescraper import db

    conn = db.connect(db.init_db())
    try:
        typer.echo(f"Firms by status: {db.firm_status_summary(conn)}")
        typer.echo(f"Jobs by status: {db.queue_summary(conn)}")
    finally:
        conn.close()


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
