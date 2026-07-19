"""pescraper command-line interface.

Phase 1 skeleton: the command surface (run, run-firm, export, status, doctor,
init-db) is the stable seam that later phases and the Windows Task Scheduler /
nanoclaw orchestration invoke. The four data-pipeline commands are stubs here;
real behavior arrives in later phases.

Importing this module imports ``pescraper``, which activates the Windows runtime
hardening (Proactor policy + UTF-8) as a side effect, so the console entry point
runs under the hardened runtime.

``doctor`` and ``init-db`` deliberately import their implementation modules
(``pescraper.doctor`` / ``pescraper.db``) *lazily inside the function body*. Those
modules land in wave 2; keeping the imports lazy means ``pescraper --help`` and
every stub work now, before those modules exist.
"""

from __future__ import annotations

import logging
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

    from pescraper import confidence, crawl, db, decongest, extract, merge, models, provenance

    pages = await crawl.select_pages(url)

    if not pages:
        logger.warning("needs_review: no_criteria_page (%s)", url)
        record = models.FirmRecord(
            firm_name=_derive_firm_name(url),
            website=url,
            needs_review=True,
            status=models.FirmStatus.NEEDS_REVIEW,
        )
        return record, []

    financial = await extract.extract_financial(pages)
    categorical = await extract.extract_categorical(pages)

    provenance_rows: list[dict] = []
    quote_sources = (
        (financial, _FINANCIAL_QUOTE_TO_VALUE, "financial_v1"),
        (categorical, _CATEGORICAL_QUOTE_TO_VALUE, "categorical_v1"),
    )
    for source, quote_map, prompt_version in quote_sources:
        for quote_field, value_field in quote_map.items():
            quote_value = getattr(source, quote_field, None)
            if not quote_value:
                continue
            value = getattr(source, value_field, None)
            source_page_url = provenance.find_source_page(quote_value, pages)
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


@app.command()
def run() -> None:
    """Run the batch pipeline over the queued firms (Phase 1 skeleton)."""
    typer.echo("pescraper run: Phase 1 skeleton — batch pipeline lands in a later phase.")


@app.command("run-firm")
def run_firm(url: str = typer.Argument(..., help="Firm website URL to research.")) -> None:
    """Research a single firm by URL (Phase 1 skeleton)."""
    typer.echo(f"pescraper run-firm {url}: Phase 1 skeleton — single-firm research lands in a later phase.")


@app.command()
def export() -> None:
    """Export the dataset to Excel/CSV (Phase 1 skeleton)."""
    typer.echo("pescraper export: Phase 1 skeleton — export lands in a later phase.")


@app.command()
def status() -> None:
    """Show pipeline/queue status (Phase 1 skeleton)."""
    typer.echo("pescraper status: Phase 1 skeleton — status reporting lands in a later phase.")


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
