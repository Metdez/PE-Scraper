"""Null-safe field merging and range-conflict detection.

Pure functions, zero I/O. This is the single source of truth for the merge rule
CONTEXT.md requires to be universal (applied on every write path — seed-time AND
any future re-extraction): a new value only overwrites an existing one if it is
non-null; null never clears a previously confirmed value.
"""

from __future__ import annotations

from typing import Any

from pescraper.models import FIRM_COLUMNS, FirmRecord

LIFECYCLE_FIELDS = frozenset({"status", "confidence", "needs_review", "last_checked"})

RANGE_FIELD_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("rev_min_musd", "rev_max_musd", "rev"),
    ("ebitda_min_musd", "ebitda_max_musd", "ebitda"),
    ("ev_min_musd", "ev_max_musd", "ev"),
    ("check_min_musd", "check_max_musd", "check"),
)


def merge_field(existing: Any, new: Any) -> Any:
    """Return ``new`` if non-null, else ``existing``. Null never clears data."""
    return new if new is not None else existing


def ranges_conflict(
    seed_lo: float | None,
    seed_hi: float | None,
    extracted_lo: float | None,
    extracted_hi: float | None,
) -> bool:
    """True only when the two ranges share zero overlap.

    Any missing input means no conflict can be determined (returns False).
    Nested/overlapping ranges are agreement, not conflict.
    """
    if None in (seed_lo, seed_hi, extracted_lo, extracted_hi):
        return False
    return extracted_hi < seed_lo or extracted_lo > seed_hi


def merge_firm_record(
    existing: FirmRecord | None, new: FirmRecord
) -> tuple[FirmRecord, list[str]]:
    """Merge ``new`` onto ``existing`` per the universal null-safe rule.

    Brand-new firm (``existing is None``): returns ``new`` unchanged, no conflicts.
    Otherwise every field except the lifecycle set is merged via ``merge_field``;
    lifecycle fields are copied unchanged from ``existing`` (callers decide those
    explicitly). Range-field pairs are checked for conflicts and reported by name.
    """
    if existing is None:
        return new, []

    existing_data = existing.model_dump()
    new_data = new.model_dump()
    merged: dict[str, Any] = {}

    for field in FIRM_COLUMNS:
        if field in LIFECYCLE_FIELDS:
            merged[field] = existing_data[field]
        else:
            merged[field] = merge_field(existing_data[field], new_data[field])

    conflicts: list[str] = []
    for lo_field, hi_field, name in RANGE_FIELD_PAIRS:
        if ranges_conflict(
            existing_data[lo_field],
            existing_data[hi_field],
            new_data[lo_field],
            new_data[hi_field],
        ):
            conflicts.append(name)

    return FirmRecord(**merged), conflicts


__all__ = [
    "LIFECYCLE_FIELDS",
    "RANGE_FIELD_PAIRS",
    "merge_field",
    "ranges_conflict",
    "merge_firm_record",
]
