"""Null-safe field merge and range-conflict detection — the merge-rule contract.

Pure functions only: no sqlite3, no ollama, no crawl4ai imports. Per
02-CONTEXT.md ("Capital IQ Seeding & Merge Rules"), this module is the single
source of truth for the merge rule and must be reused (not re-implemented) by
``ingest.py`` (02-05) and ``cli.py`` (02-06) on every write path — initial
Capital IQ seed merge AND any future re-extraction on a stale re-check.

Universal rule: a new value only overwrites an existing field if the new
value is non-null. Null never clears a previously confirmed value.
"""

from __future__ import annotations

from typing import Any, Optional

from pescraper.models import FirmRecord

# Lifecycle fields are never touched by the generic per-field merge pass —
# callers (ingest.py, cli.py) decide status/confidence/needs_review/
# last_checked explicitly; they are copied unchanged from `existing` here.
LIFECYCLE_FIELDS: frozenset[str] = frozenset(
    {"status", "confidence", "needs_review", "last_checked"}
)

# (min_field, max_field, short_name) for each of the four numeric range pairs
# that participate in seed-vs-extraction conflict detection.
RANGE_FIELD_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("rev_min_musd", "rev_max_musd", "rev"),
    ("ebitda_min_musd", "ebitda_max_musd", "ebitda"),
    ("ev_min_musd", "ev_max_musd", "ev"),
    ("check_min_musd", "check_max_musd", "check"),
)


def merge_field(existing: Any, new: Any) -> Any:
    """Return ``new`` if it is non-null, else ``existing``.

    New always wins when non-null, even over a confirmed existing value.
    Null never clears a previously confirmed value.
    """
    return new if new is not None else existing


def ranges_conflict(
    seed_lo: Optional[float],
    seed_hi: Optional[float],
    extracted_lo: Optional[float],
    extracted_hi: Optional[float],
) -> bool:
    """True only when the two ranges share zero overlap.

    Any ``None`` input means a conflict cannot be determined -> False.
    Nested/overlapping ranges (including touching boundaries) -> False
    (agreement, not conflict) per 02-CONTEXT.md.
    """
    if None in (seed_lo, seed_hi, extracted_lo, extracted_hi):
        return False
    return extracted_hi < seed_lo or extracted_lo > seed_hi


def merge_firm_record(
    existing: Optional[FirmRecord], new: FirmRecord
) -> tuple[FirmRecord, list[str]]:
    """Merge ``new`` into ``existing`` using the null-safe field rule.

    If ``existing`` is None, this is a brand-new firm: return ``(new, [])``
    unchanged. Otherwise, for every field except the lifecycle set, apply
    ``merge_field``; lifecycle fields are copied unchanged from ``existing``.
    For each of the four range-field pairs, detect disjoint-range conflicts
    and collect their short names into the returned conflicts list.
    """
    if existing is None:
        return new, []

    merged_fields: dict[str, Any] = {}
    for field_name in FirmRecord.model_fields:
        if field_name in LIFECYCLE_FIELDS:
            merged_fields[field_name] = getattr(existing, field_name)
        else:
            merged_fields[field_name] = merge_field(
                getattr(existing, field_name), getattr(new, field_name)
            )

    conflicts: list[str] = []
    for lo_field, hi_field, short_name in RANGE_FIELD_PAIRS:
        if ranges_conflict(
            getattr(existing, lo_field),
            getattr(existing, hi_field),
            getattr(new, lo_field),
            getattr(new, hi_field),
        ):
            conflicts.append(short_name)

    return FirmRecord(**merged_fields), conflicts


__all__ = [
    "LIFECYCLE_FIELDS",
    "RANGE_FIELD_PAIRS",
    "merge_field",
    "ranges_conflict",
    "merge_firm_record",
]
