"""Tests for pescraper.confidence — code-computed confidence and needs-review.

Pure-function contract (no I/O, no LLM): see
.planning/phases/02-core-pipeline-single-firm/02-01-PLAN.md Task 2 and
02-CONTEXT.md "Confidence Scoring & Needs Review".
"""

from __future__ import annotations


def _make_record(**overrides):
    from pescraper.models import FirmRecord

    base = {"firm_name": "Acme Capital"}
    base.update(overrides)
    return FirmRecord(**base)


# --------------------------------------------------------------------------- #
# POPULATABLE_FIELDS / CORE_NUMERIC_FIELDS constants
# --------------------------------------------------------------------------- #


def test_populatable_fields_excludes_fund_name_last_deal_and_lifecycle_fields() -> None:
    from pescraper.confidence import POPULATABLE_FIELDS

    excluded = {
        "firm_name",
        "fund_name",
        "last_deal",
        "confidence",
        "needs_review",
        "last_checked",
        "status",
    }
    assert not (set(POPULATABLE_FIELDS) & excluded)
    assert len(POPULATABLE_FIELDS) == 17


def test_core_numeric_fields_is_the_six_financial_range_fields() -> None:
    from pescraper.confidence import CORE_NUMERIC_FIELDS

    assert set(CORE_NUMERIC_FIELDS) == {
        "ebitda_min_musd",
        "ebitda_max_musd",
        "ev_min_musd",
        "ev_max_musd",
        "check_min_musd",
        "check_max_musd",
    }


# --------------------------------------------------------------------------- #
# compute_confidence
# --------------------------------------------------------------------------- #


def test_compute_confidence_zero_populated_fields_is_zero() -> None:
    from pescraper.confidence import compute_confidence

    record = _make_record()
    assert compute_confidence(record) == 0.0


def test_compute_confidence_all_populatable_fields_is_one() -> None:
    from pescraper.confidence import POPULATABLE_FIELDS, compute_confidence

    values: dict[str, object] = {}
    for field_name in POPULATABLE_FIELDS:
        if field_name == "us_investments":
            values[field_name] = 5
        elif field_name.endswith("_musd"):
            values[field_name] = 10.0
        else:
            values[field_name] = "some value"
    record = _make_record(**values)

    assert compute_confidence(record) == 1.0


def test_compute_confidence_roughly_half_populated_is_about_half() -> None:
    from pescraper.confidence import POPULATABLE_FIELDS, compute_confidence

    half = len(POPULATABLE_FIELDS) // 2
    values: dict[str, object] = {}
    for field_name in POPULATABLE_FIELDS[:half]:
        if field_name == "us_investments":
            values[field_name] = 5
        elif field_name.endswith("_musd"):
            values[field_name] = 10.0
        else:
            values[field_name] = "some value"
    record = _make_record(**values)

    confidence = compute_confidence(record)
    assert abs(confidence - (half / len(POPULATABLE_FIELDS))) < 1e-9


def test_compute_confidence_ignores_fund_name_and_last_deal() -> None:
    from pescraper.confidence import compute_confidence

    without = _make_record()
    with_excluded = _make_record(fund_name="Fund III", last_deal="2025 platform deal")

    # Populating only the excluded fields must not move the ratio off zero.
    assert compute_confidence(without) == compute_confidence(with_excluded) == 0.0


# --------------------------------------------------------------------------- #
# is_needs_review
# --------------------------------------------------------------------------- #


def test_is_needs_review_true_when_zero_core_numerics_even_above_threshold() -> None:
    from pescraper.confidence import is_needs_review

    # confidence=0.35 >= 0.3, but all six CORE_NUMERIC_FIELDS are None — the
    # zero-core-numerics OR-branch fires independent of the ratio.
    record = _make_record(type="Buyout", state="IL", city="Chicago")
    assert is_needs_review(record, confidence=0.35) is True


def test_is_needs_review_true_when_confidence_below_threshold() -> None:
    from pescraper.confidence import is_needs_review

    record = _make_record(ebitda_min_musd=5.0, ebitda_max_musd=25.0)
    assert is_needs_review(record, confidence=0.1) is True


def test_is_needs_review_false_when_above_threshold_and_core_numeric_populated() -> None:
    from pescraper.confidence import is_needs_review

    record = _make_record(ebitda_min_musd=5.0, ebitda_max_musd=25.0)
    assert is_needs_review(record, confidence=0.5) is False
