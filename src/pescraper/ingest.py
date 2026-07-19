"""Capital IQ CSV ingest: flexible column mapping + free-text range parsing.

Applies only to the CSV-batch path (Phase 4), never to ``run-firm <url>`` (no CSV
row exists for an ad-hoc URL, per CONTEXT.md). The real Capital IQ export isn't
available yet — this is built against the documented expected 24-column-aligned
shape (Requirements.md's sample rows) with a flexible, case-insensitive mapper
plus known header aliases, reconciled against the real export when it arrives.

Clean numeric cells pass through as a no-op; only genuinely free-text range cells
(e.g. an "EBITDA Range" column like ``"$5-25M"``) need the regex split.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from pescraper.models import FirmRecord

logger = logging.getLogger(__name__)

RANGE_RE = re.compile(r"\$?\s*([\d.]+)\s*(?:-|to)\s*\$?\s*([\d.]+)\s*([MB]?)", re.IGNORECASE)

# Header (lowercased, stripped) -> canonical FIRM_COLUMNS field name.
DIRECT_COLUMN_ALIASES: dict[str, str] = {
    "firm name": "firm_name",
    "firm": "firm_name",
    "company": "firm_name",
    "company name": "firm_name",
    "type": "type",
    "state": "state",
    "city": "city",
    "website": "website",
    "url": "website",
    "web site": "website",
    "us investments": "us_investments",
    "us investment": "us_investments",
    "rev min ($m)": "rev_min_musd",
    "rev min": "rev_min_musd",
    "revenue min": "rev_min_musd",
    "rev max ($m)": "rev_max_musd",
    "rev max": "rev_max_musd",
    "revenue max": "rev_max_musd",
    "ebitda min ($m)": "ebitda_min_musd",
    "ebitda min": "ebitda_min_musd",
    "ebitda max ($m)": "ebitda_max_musd",
    "ebitda max": "ebitda_max_musd",
    "ev min ($m)": "ev_min_musd",
    "ev min": "ev_min_musd",
    "ev max ($m)": "ev_max_musd",
    "ev max": "ev_max_musd",
    "check min ($m)": "check_min_musd",
    "check min": "check_min_musd",
    "check max ($m)": "check_max_musd",
    "check max": "check_max_musd",
    "deal types": "deal_types",
    "deal type": "deal_types",
    "sector tier 1": "sector_tier1",
    "sector": "sector_tier1",
    "aum ($m)": "aum_musd",
    "aum": "aum_musd",
    "activity": "activity",
    "last deal": "last_deal",
    "fund name": "fund_name",
    "confidence": "confidence",
    "needs review": "needs_review",
    "last checked": "last_checked",
    "status": "status",
}

# Header (lowercased, stripped) -> (min_field, max_field) for combined free-text
# range cells, e.g. "EBITDA Range" -> "$5-25M".
RANGE_COLUMN_ALIASES: dict[str, tuple[str, str]] = {
    "ebitda range": ("ebitda_min_musd", "ebitda_max_musd"),
    "revenue range": ("rev_min_musd", "rev_max_musd"),
    "rev range": ("rev_min_musd", "rev_max_musd"),
    "ev range": ("ev_min_musd", "ev_max_musd"),
    "enterprise value range": ("ev_min_musd", "ev_max_musd"),
    "check size": ("check_min_musd", "check_max_musd"),
    "check size range": ("check_min_musd", "check_max_musd"),
}

_MUSD_FIELDS = frozenset(
    {
        "rev_min_musd",
        "rev_max_musd",
        "ebitda_min_musd",
        "ebitda_max_musd",
        "ev_min_musd",
        "ev_max_musd",
        "check_min_musd",
        "check_max_musd",
        "aum_musd",
    }
)


def parse_range(cell: str | None) -> tuple[float | None, float | None]:
    """Parse a free-text range cell like ``"$5-25M"`` into ``(5.0, 25.0)``.

    A blank/None cell returns ``(None, None)``. A cell that doesn't match the
    range pattern also returns ``(None, None)`` (clean numeric cells are not
    routed through this function — see ``row_to_firm_record``).
    """
    if cell is None or cell.strip() == "":
        return None, None
    match = RANGE_RE.search(cell)
    if not match:
        return None, None
    lo, hi, unit = float(match.group(1)), float(match.group(2)), match.group(3).upper()
    if unit == "B":
        lo, hi = lo * 1000, hi * 1000
    return lo, hi


def _normalize_header(header: str) -> str:
    return header.strip().lower()


def _coerce(field: str, raw: str) -> object:
    value = raw.strip() if raw is not None else ""
    if value == "":
        return None
    if field in _MUSD_FIELDS or field == "confidence":
        try:
            return float(value)
        except ValueError:
            return None
    if field == "us_investments":
        try:
            return int(float(value))
        except ValueError:
            return None
    if field == "needs_review":
        return value.lower() in {"yes", "true", "1"}
    return value


def row_to_firm_record(row: dict[str, str]) -> FirmRecord | None:
    """Map one raw CSV row (arbitrary header casing) to a FirmRecord.

    Returns None if the row has no usable firm_name (an un-ingestable row is
    skipped, not a hard failure for the whole file).
    """
    fields: dict[str, object] = {}

    for raw_header, raw_value in row.items():
        if raw_header is None:
            continue
        header = _normalize_header(raw_header)

        if header in DIRECT_COLUMN_ALIASES:
            field = DIRECT_COLUMN_ALIASES[header]
            fields[field] = _coerce(field, raw_value or "")

    for raw_header, raw_value in row.items():
        if raw_header is None:
            continue
        header = _normalize_header(raw_header)
        if header in RANGE_COLUMN_ALIASES:
            min_field, max_field = RANGE_COLUMN_ALIASES[header]
            lo, hi = parse_range(raw_value)
            if fields.get(min_field) is None and lo is not None:
                fields[min_field] = lo
            if fields.get(max_field) is None and hi is not None:
                fields[max_field] = hi

    firm_name = fields.get("firm_name")
    if not firm_name:
        logger.warning("skipping CSV row with no usable firm_name: %r", row)
        return None

    # status/needs_review/confidence/last_checked are lifecycle fields the CSV
    # may not carry meaningfully — only pass through what was actually mapped.
    return FirmRecord(**fields)


def ingest_csv(path: str | Path) -> list[FirmRecord]:
    """Read a Capital IQ-shaped CSV and return one FirmRecord per usable row."""
    records: list[FirmRecord] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            record = row_to_firm_record(row)
            if record is not None:
                records.append(record)
    return records


__all__ = [
    "RANGE_RE",
    "DIRECT_COLUMN_ALIASES",
    "RANGE_COLUMN_ALIASES",
    "parse_range",
    "row_to_firm_record",
    "ingest_csv",
]
