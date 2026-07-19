"""Code-computed confidence and needs-review threshold.

Deterministic, explainable, never an LLM self-report (per ROADMAP). Pure functions,
zero I/O.
"""

from __future__ import annotations

from pescraper.models import FirmRecord

# Criteria fields the ratio is computed over. Excludes firm_name (always populated,
# not a criteria signal), fund_name/last_deal (commonly absent per CONTEXT.md), and
# the metadata/lifecycle fields (confidence, needs_review, last_checked, status).
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

CORE_NUMERIC_FIELDS: tuple[str, ...] = (
    "ebitda_min_musd",
    "ebitda_max_musd",
    "ev_min_musd",
    "ev_max_musd",
    "check_min_musd",
    "check_max_musd",
)

NEEDS_REVIEW_THRESHOLD = 0.3


def compute_confidence(record: FirmRecord) -> float:
    """Ratio of populated POPULATABLE_FIELDS to the total, in [0.0, 1.0]."""
    data = record.model_dump()
    populated = sum(1 for f in POPULATABLE_FIELDS if data[f] is not None)
    return populated / len(POPULATABLE_FIELDS)


def is_needs_review(record: FirmRecord, confidence: float) -> bool:
    """True when confidence < 0.3 OR zero core numeric fields are populated."""
    data = record.model_dump()
    zero_core_numerics = all(data[f] is None for f in CORE_NUMERIC_FIELDS)
    return confidence < NEEDS_REVIEW_THRESHOLD or zero_core_numerics


__all__ = [
    "POPULATABLE_FIELDS",
    "CORE_NUMERIC_FIELDS",
    "NEEDS_REVIEW_THRESHOLD",
    "compute_confidence",
    "is_needs_review",
]
