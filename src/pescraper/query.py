"""Freeform-ish dataset queries — the CLI equivalent of nanoclaw's "ask the
dataset" chat skill (Phase 5, Windows-native pivot: structured filters instead
of an LLM chat loop). Pure function over already-loaded FirmRecords, no I/O.
"""

from __future__ import annotations

from pescraper.models import FirmRecord


def _range_overlaps(f_lo, f_hi, q_lo, q_hi) -> bool:
    if f_lo is None and f_hi is None:
        return False
    lo = f_lo if f_lo is not None else float("-inf")
    hi = f_hi if f_hi is not None else float("inf")
    return not (hi < q_lo or lo > q_hi)


def find_firms(
    records: list[FirmRecord],
    *,
    state: str | None = None,
    sector: str | None = None,
    deal_type: str | None = None,
    ebitda_min: float | None = None,
    ebitda_max: float | None = None,
    rev_min: float | None = None,
    rev_max: float | None = None,
    needs_review: bool | None = None,
) -> list[FirmRecord]:
    """Filter firms by state/sector/deal-type substring match and numeric range overlap."""
    results = []
    for r in records:
        if state and (r.state or "").lower() != state.lower():
            continue
        if sector and sector.lower() not in (r.sector_tier1 or "").lower():
            continue
        if deal_type and deal_type.lower() not in (r.deal_types or "").lower():
            continue
        if needs_review is not None and r.needs_review != needs_review:
            continue
        if (ebitda_min is not None or ebitda_max is not None) and not _range_overlaps(
            r.ebitda_min_musd,
            r.ebitda_max_musd,
            ebitda_min if ebitda_min is not None else float("-inf"),
            ebitda_max if ebitda_max is not None else float("inf"),
        ):
            continue
        if (rev_min is not None or rev_max is not None) and not _range_overlaps(
            r.rev_min_musd,
            r.rev_max_musd,
            rev_min if rev_min is not None else float("-inf"),
            rev_max if rev_max is not None else float("inf"),
        ):
            continue
        results.append(r)
    return results


__all__ = ["find_firms"]
