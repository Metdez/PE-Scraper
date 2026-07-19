"""Code-computed confidence and needs-review threshold — never an LLM self-report.

Per 02-CONTEXT.md ("Confidence Scoring & Needs Review"): confidence is a
deterministic ratio of populated criteria fields, and ``needs_review`` fires
either when that ratio is below threshold OR when zero core numeric
(EBITDA/EV/check size) fields are populated at all — independent conditions,
combined with OR. Pure functions only: no I/O, no LLM.
"""

from __future__ import annotations

from pescraper.models import FirmRecord

# Criteria fields that typically get populated by extraction/seeding. Excludes
# firm_name (always present, not a criteria signal), fund_name/last_deal
# ("commonly absent" per CONTEXT.md — excluding them from the denominator
# keeps the ratio meaningful), and the metadata/lifecycle fields (confidence,
# needs_review, last_checked, status), which aren't criteria fields at all.
POPULATABLE_FIELDS: tuple[str, ...] = (
    "type",
    "state",
    "city",
    "website",
    "us_investments",
    "rev_min_musd",
    "rev_max_musd",
    "ebitda_min_musd",
    "ebitda_max_musd",
    "ev_min_musd",
    "ev_max_musd",
    "check_min_musd",
    "check_max_musd",
    "deal_types",
    "sector_tier1",
    "aum_musd",
    "activity",
)

# The six financial-range fields that gate the "zero core numerics" branch of
# is_needs_review — EBITDA, EV, and check-size min/max.
CORE_NUMERIC_FIELDS: tuple[str, ...] = (
    "ebitda_min_musd",
    "ebitda_max_musd",
    "ev_min_musd",
    "ev_max_musd",
    "check_min_musd",
    "check_max_musd",
)

NEEDS_REVIEW_THRESHOLD: float = 0.3


def compute_confidence(record: FirmRecord) -> float:
    """Ratio of non-null POPULATABLE_FIELDS on ``record``.

    0.0 when nothing is populated, 1.0 when everything is populated.
    Deterministic, explainable, code-computed — never an LLM self-report.
    """
    populated = sum(
        1 for field_name in POPULATABLE_FIELDS if getattr(record, field_name) is not None
    )
    return populated / len(POPULATABLE_FIELDS)


def is_needs_review(record: FirmRecord, confidence: float) -> bool:
    """True when ``confidence`` is below threshold OR zero core numerics are populated.

    These are independent OR-branches: a record can clear the confidence
    threshold and still be flagged needs_review if it has no EBITDA/EV/check
    size data at all, and a record can have core numerics populated but still
    be flagged if the overall confidence ratio is too low.
    """
    below_threshold = confidence < NEEDS_REVIEW_THRESHOLD
    zero_core_numerics = all(
        getattr(record, field_name) is None for field_name in CORE_NUMERIC_FIELDS
    )
    return below_threshold or zero_core_numerics


__all__ = [
    "POPULATABLE_FIELDS",
    "CORE_NUMERIC_FIELDS",
    "NEEDS_REVIEW_THRESHOLD",
    "compute_confidence",
    "is_needs_review",
]
