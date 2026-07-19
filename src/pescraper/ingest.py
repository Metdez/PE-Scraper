"""Capital IQ CSV seed ingest — column mapper, free-text range regex, orchestrator.

Per 02-CONTEXT.md ("Capital IQ Seeding & Merge Rules"), this module is built
with a flexible, case-insensitive column mapper. ``COLUMN_ALIASES`` covers both
the originally-assumed shape and the verified real Capital IQ export headers
(reconciled against ``data/capiq_test.csv``), including its embedded-newline
"Assets Under Management\n($000)" / "Total Investments\n(actual)" headers.

Two responsibilities:

1. Pure parsing helpers (``parse_range``, ``map_columns``) — no I/O, unit
   tested in isolation (Task 1).
2. ``ingest_csv`` — the orchestrator that streams a CSV, seeds ``FirmRecord``
   rows, and merges them into ``pipeline.db`` via ``merge.merge_firm_record``
   (02-01), the single source of truth for the null-safe merge rule. This is
   the ONLY place besides a future re-extraction path (02-06/Phase 4) that
   should ever call ``merge_firm_record`` — never re-implement the rule here.

Deliberately NOT wired into ``cli.py``'s ``run_firm(url)``: an ad-hoc single
URL has no CSV row to consult (per CONTEXT.md). Seeding applies only to the
future CSV-batch path (Phase 4), which will import ``ingest_csv`` directly.
"""

from __future__ import annotations

import csv
import dataclasses
import logging
import re
import sqlite3
import typing
from pathlib import Path
from typing import Any

from pescraper import db, merge
from pescraper.models import FirmRecord

logger = logging.getLogger(__name__)


def _unwrap_optional(annotation: Any) -> Any:
    """Unwrap ``Optional[X]`` (``Union[X, None]``) down to ``X``; pass through otherwise."""
    args = typing.get_args(annotation)
    non_none = [a for a in args if a is not type(None)]
    if len(non_none) == 1:
        return non_none[0]
    return annotation


# Field names whose FirmRecord annotation is int or float (Optional-unwrapped).
# Capital IQ emits thousands-separator commas in some integer columns (e.g.
# "Total Investments (actual)" -> "1,238"), which Pydantic's int/float coercion
# cannot parse directly. Stripping commas generically for these fields (rather
# than special-casing us_investments alone) keeps the fix applicable to any
# numeric direct-field column a future CSV might introduce.
_NUMERIC_FIELD_NAMES: frozenset[str] = frozenset(
    name
    for name, field in FirmRecord.model_fields.items()
    if _unwrap_optional(field.annotation) in (int, float)
)


# --------------------------------------------------------------------------- #
# Free-text range regex parser
# --------------------------------------------------------------------------- #

# Two numbers separated by a hyphen or the word "to"/"through", each with an
# optional leading "$" and an optional trailing M/B unit suffix (case
# insensitive). Example matches: "$5-25M", "$1.5B - $2B", "5 to 25".
_RANGE_RE = re.compile(
    r"\$?\s*([\d,]*\.?\d+)\s*([MB])?\s*(?:-|to|through)\s*\$?\s*([\d,]*\.?\d+)\s*([MB])?",
    re.IGNORECASE,
)

# A single bare number, optional leading "$" and optional trailing M/B unit
# suffix. Used as the fallback when no range separator is present.
_SINGLE_RE = re.compile(r"\$?\s*([\d,]*\.?\d+)\s*([MB])?", re.IGNORECASE)


def _to_musd(value: float, unit: str | None) -> float:
    """Apply the B->M unit conversion (x1000); M or no unit is a no-op."""
    if unit and unit.upper() == "B":
        return value * 1000.0
    return value


def parse_range(cell: str | None) -> tuple[float | None, float | None]:
    """Parse a free-text CSV range cell into ``(min, max)`` in $M USD.

    ``"$5-25M" -> (5.0, 25.0)``. ``"$1.5B - $2B" -> (1500.0, 2000.0)`` (each
    side's own unit suffix is honored independently). A clean/already-numeric
    cell is not mangled -- it passes through unchanged as ``(v, v)``.

    Claude's-discretion behavior (documented per PLAN.md Task 1 action): a
    bare number with no range separator is treated as BOTH min and max --
    ``parse_range("15") -> (15.0, 15.0)`` -- since a single confirmed figure
    is still a confirmed data point, not a range, and dropping it entirely
    would silently lose real seed data.

    ``None`` and empty/whitespace-only input both return ``(None, None)``.
    """
    if cell is None:
        return None, None
    text = cell.strip()
    if text == "":
        return None, None

    range_match = _RANGE_RE.search(text)
    if range_match:
        lo_str, lo_unit, hi_str, hi_unit = range_match.groups()
        # If only one side carries a unit suffix ("$5-25M"), the other side
        # inherits it -- the common CSV shorthand.
        if not lo_unit and hi_unit:
            lo_unit = hi_unit
        elif not hi_unit and lo_unit:
            hi_unit = lo_unit
        lo = _to_musd(float(lo_str.replace(",", "")), lo_unit)
        hi = _to_musd(float(hi_str.replace(",", "")), hi_unit)
        return lo, hi

    single_match = _SINGLE_RE.search(text)
    if single_match:
        val_str, unit = single_match.groups()
        val = _to_musd(float(val_str.replace(",", "")), unit)
        return val, val

    return None, None


# --------------------------------------------------------------------------- #
# Column mapper
# --------------------------------------------------------------------------- #

# Cells whose stripped, case-folded value mean "missing" across the whole
# ingest pipeline -- both the direct-field coercion pass in ingest_csv and the
# _capiq_website/_capiq_aum_thousands pseudo-key normalization blocks share
# this single sentinel set so "NA"/"N/A" (Capital IQ's missing-value
# convention) and plain empty string are never duplicated as inline literals.
_MISSING_SENTINELS: frozenset[str] = frozenset({"", "na", "n/a"})

# Known header aliases, per RESEARCH.md Pattern 7, extended with a reasonable
# alias set (Claude's discretion per CONTEXT.md) covering identity, location,
# classification, AUM, and the four free-text range columns. Range columns
# map to internal pseudo-keys prefixed "_" -- ingest_csv routes these through
# parse_range and splits them into the matching *_min_musd/*_max_musd fields.
COLUMN_ALIASES: dict[str, str] = {
    # Identity
    "firm name": "firm_name",
    "firm": "firm_name",
    "company": "firm_name",
    "company name": "firm_name",
    "entity name": "firm_name",
    "website": "website",
    "url": "website",
    "web site": "website",
    "web": "website",
    # Capital IQ exports bare domains in this column. Route it through a
    # dedicated pseudo-key so ingest_csv can add the URL scheme without
    # changing the established behavior of generic Website/URL columns.
    "web address": "_capiq_website",
    # Location
    "state": "state",
    "hq state": "state",
    "city": "city",
    "hq city": "city",
    # Classification
    "type": "type",
    "firm type": "type",
    "sector": "sector_tier1",
    "sector tier 1": "sector_tier1",
    "sector emphasis": "sector_tier1",
    "industry": "sector_tier1",
    "deal type": "deal_types",
    "deal types": "deal_types",
    # AUM
    "aum": "aum_musd",
    "aum ($m)": "aum_musd",
    "aum musd": "aum_musd",
    # Capital IQ reports AUM in $000s under a header that wraps its unit onto
    # a second line inside the cell itself. Routed through a pseudo-key (like
    # _capiq_website above) because the $000s -> $M scale conversion is more
    # than the generic direct-field pass can apply.
    "assets under management ($000)": "_capiq_aum_thousands",
    # Capital IQ's investment-count header wraps its unit onto a second line
    # ("(actual)"); needs no transform beyond NA-as-null coercion since
    # Pydantic already coerces a numeric string like "49" to int.
    "total investments (actual)": "us_investments",
    # Free-text range pseudo-keys (routed through parse_range by ingest_csv)
    "rev range": "_rev_range",
    "revenue range": "_rev_range",
    "revenue": "_rev_range",
    "ebitda range": "_ebitda_range",
    "ebitda": "_ebitda_range",
    "ev range": "_ev_range",
    "enterprise value range": "_ev_range",
    "enterprise value": "_ev_range",
    "check size": "_check_range",
    "check range": "_check_range",
    "check": "_check_range",
}

# Maps each range pseudo-key to the (min_field, max_field) pair it seeds.
_RANGE_KEY_TO_FIELDS: dict[str, tuple[str, str]] = {
    "_rev_range": ("rev_min_musd", "rev_max_musd"),
    "_ebitda_range": ("ebitda_min_musd", "ebitda_max_musd"),
    "_ev_range": ("ev_min_musd", "ev_max_musd"),
    "_check_range": ("check_min_musd", "check_max_musd"),
}


# Collapses one-or-more whitespace characters (including embedded newlines)
# to a single space. Capital IQ wraps a column's unit onto a second physical
# line inside the header cell itself (e.g. "Assets Under Management\n($000)"),
# so a plain .strip().lower() never produces a string a single-line alias key
# can match -- this normalization is applied generally, not special-cased to
# any particular header.
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def map_columns(header: list[str]) -> dict[str, str]:
    """Map a CSV header row to normalized internal keys.

    Each header is stripped, lowercased, and whitespace-collapsed (internal
    runs of whitespace -- including embedded newlines -- become a single
    space) before the case-insensitive ``COLUMN_ALIASES`` lookup. An
    unrecognized header passes through as its own normalized key rather than
    raising or being silently dropped (Claude's discretion per CONTEXT.md) --
    this keeps future real-CSV reconciliation additive rather than a rewrite.
    """
    normalized_headers = {h: _WHITESPACE_RUN_RE.sub(" ", h.strip().lower()) for h in header}
    return {h: COLUMN_ALIASES.get(norm, norm) for h, norm in normalized_headers.items()}


# --------------------------------------------------------------------------- #
# ingest_csv orchestrator
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class IngestSummary:
    """Counters returned by :func:`ingest_csv` for a single ingest run."""

    rows_read: int = 0
    rows_seeded: int = 0
    rows_skipped: int = 0
    rows_conflicted: int = 0


def ingest_csv(csv_path: str | Path, conn: sqlite3.Connection) -> IngestSummary:
    """Stream a Capital IQ-shaped CSV and seed ``pipeline.db`` via the universal merge rule.

    Opens the CSV with stdlib ``csv.DictReader`` (streaming, never loads the
    whole file into memory), maps the header once via :func:`map_columns`,
    then per row: builds a normalized field dict (direct FirmRecord-field
    columns take precedence; free-text range pseudo-keys are parsed via
    :func:`parse_range` only when the matching clean *_min_musd/*_max_musd
    columns are absent), skips the row if neither ``firm_name`` nor
    ``website`` is present, constructs a seed ``FirmRecord``, merges it
    against any existing row via ``merge.merge_firm_record`` (02-01), sets
    ``needs_review = True`` on the merged record when a range conflict is
    reported (an explicit caller-side override -- merge_firm_record's generic
    lifecycle pass-through does not itself flag conflicts, per CONTEXT.md),
    and upserts via ``db.upsert_firm``.
    """
    summary = IngestSummary()
    path = Path(csv_path)

    # ``utf-8-sig`` accepts ordinary UTF-8 and strips the BOM emitted by
    # Capital IQ exports, keeping the first header (Entity Name) matchable.
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return summary

        column_map = map_columns(list(reader.fieldnames))

        for row in reader:
            summary.rows_read += 1

            normalized: dict[str, str] = {}
            for original, raw_value in row.items():
                if original is None:
                    continue
                key = column_map.get(original, original.strip().lower())
                normalized[key] = raw_value if raw_value is not None else ""

            field_values: dict[str, Any] = {}

            # First pass: direct FirmRecord-field columns (includes clean
            # numeric *_min_musd/*_max_musd columns, if the CSV supplies them).
            # A cell whose stripped value case-insensitively matches
            # _MISSING_SENTINELS (empty string, or Capital IQ's "NA"/"N/A"
            # missing-value convention) becomes None before it ever reaches
            # FirmRecord(**field_values) -- otherwise a literal "NA" in a
            # numeric column raises a Pydantic validation error and silently
            # drops the whole row.
            for key, raw_value in normalized.items():
                if key.startswith("_"):
                    continue  # range pseudo-keys handled in the second pass
                if key not in FirmRecord.model_fields:
                    continue  # not part of the 24-column schema -- ignore
                value = raw_value.strip() if isinstance(raw_value, str) else raw_value
                if isinstance(value, str) and value.casefold() in _MISSING_SENTINELS:
                    value = None
                elif isinstance(value, str) and key in _NUMERIC_FIELD_NAMES:
                    # Strip thousands-separator commas (e.g. "1,238" -> "1238")
                    # so Pydantic's int/float coercion doesn't reject the cell.
                    value = value.replace(",", "")
                field_values[key] = value

            # Second pass: free-text range pseudo-keys -- only fill a
            # min/max pair not already populated directly above (clean
            # numeric columns take precedence over regex parsing).
            for range_key, (min_field, max_field) in _RANGE_KEY_TO_FIELDS.items():
                if range_key not in normalized:
                    continue
                if field_values.get(min_field) is not None or field_values.get(max_field) is not None:
                    continue
                lo, hi = parse_range(normalized[range_key])
                if lo is not None:
                    field_values[min_field] = lo
                if hi is not None:
                    field_values[max_field] = hi

            # Capital IQ's Web Address values are commonly `www.example.com`
            # or `example.com`. Crawl4AI requires an absolute URL, so normalize
            # only this source-specific alias while preserving generic CSV
            # website values exactly as before.
            capiq_website = normalized.get("_capiq_website", "").strip()
            if not field_values.get("website") and capiq_website.casefold() not in _MISSING_SENTINELS:
                if "://" not in capiq_website:
                    capiq_website = f"https://{capiq_website}"
                field_values["website"] = capiq_website

            # Capital IQ's AUM is denominated in $000s under the
            # _capiq_aum_thousands pseudo-key; FirmRecord.aum_musd expects the
            # $M scale, so divide by 1000 after stripping thousands-separator
            # commas. Only applied when a clean aum_musd column hasn't
            # already populated the field directly, and skipped entirely when
            # the raw cell is a missing sentinel. A malformed cell degrades
            # to a missing value rather than raising.
            aum_thousands = normalized.get("_capiq_aum_thousands", "").strip()
            if (
                field_values.get("aum_musd") is None
                and aum_thousands.casefold() not in _MISSING_SENTINELS
            ):
                try:
                    field_values["aum_musd"] = float(aum_thousands.replace(",", "")) / 1000.0
                except ValueError:
                    pass

            firm_name = field_values.get("firm_name")
            website = field_values.get("website")
            if not firm_name and not website:
                logger.warning(
                    "ingest_csv: skipping row %d -- missing both firm_name and website",
                    summary.rows_read,
                )
                summary.rows_skipped += 1
                continue
            if not firm_name:
                # FirmRecord.firm_name is required; fall back to website so a
                # website-only row isn't dropped just for lacking a name.
                field_values["firm_name"] = website

            try:
                seed_record = FirmRecord(**field_values)
            except Exception:
                logger.warning(
                    "ingest_csv: skipping malformed row %d", summary.rows_read, exc_info=True
                )
                summary.rows_skipped += 1
                continue

            existing = db.get_firm(conn, website) if website else None
            merged, conflicts = merge.merge_firm_record(existing, seed_record)
            if conflicts:
                merged.needs_review = True
                summary.rows_conflicted += 1

            db.upsert_firm(conn, merged)
            summary.rows_seeded += 1

    return summary


__all__ = [
    "COLUMN_ALIASES",
    "IngestSummary",
    "ingest_csv",
    "map_columns",
    "parse_range",
]
