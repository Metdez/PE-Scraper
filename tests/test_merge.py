"""Tests for pescraper.merge — null-safe field merge and range-conflict detection.

Pure-function contract (no I/O, no LLM, no crawl4ai): see
.planning/phases/02-core-pipeline-single-firm/02-01-PLAN.md Task 1 and
02-CONTEXT.md "Capital IQ Seeding & Merge Rules".
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# merge_field
# --------------------------------------------------------------------------- #


def test_merge_field_null_new_keeps_existing() -> None:
    from pescraper.merge import merge_field

    assert merge_field(5.0, None) == 5.0


def test_merge_field_non_null_new_always_wins_over_existing() -> None:
    from pescraper.merge import merge_field

    # New value wins even though existing was a "confirmed" non-null value.
    assert merge_field(5.0, 25.0) == 25.0


def test_merge_field_both_null_is_null() -> None:
    from pescraper.merge import merge_field

    assert merge_field(None, None) is None


def test_merge_field_existing_null_new_populates() -> None:
    from pescraper.merge import merge_field

    assert merge_field(None, 10.0) == 10.0


# --------------------------------------------------------------------------- #
# ranges_conflict
# --------------------------------------------------------------------------- #


def test_ranges_conflict_disjoint_ranges_conflict() -> None:
    from pescraper.merge import ranges_conflict

    # seed says 5-10, extracted says 20-30 — zero overlap.
    assert ranges_conflict(5.0, 10.0, 20.0, 30.0) is True


def test_ranges_conflict_disjoint_reverse_order_also_conflicts() -> None:
    from pescraper.merge import ranges_conflict

    # extracted range entirely below seed range.
    assert ranges_conflict(20.0, 30.0, 5.0, 10.0) is True


def test_ranges_conflict_overlapping_ranges_do_not_conflict() -> None:
    from pescraper.merge import ranges_conflict

    assert ranges_conflict(5.0, 25.0, 20.0, 40.0) is False


def test_ranges_conflict_nested_ranges_do_not_conflict() -> None:
    from pescraper.merge import ranges_conflict

    assert ranges_conflict(5.0, 40.0, 10.0, 20.0) is False


def test_ranges_conflict_touching_boundary_does_not_conflict() -> None:
    from pescraper.merge import ranges_conflict

    # extracted_lo == seed_hi -> not strictly greater -> no conflict (agreement at boundary).
    assert ranges_conflict(5.0, 10.0, 10.0, 20.0) is False


@pytest.mark.parametrize(
    "seed_lo, seed_hi, extracted_lo, extracted_hi",
    [
        (None, 10.0, 20.0, 30.0),
        (5.0, None, 20.0, 30.0),
        (5.0, 10.0, None, 30.0),
        (5.0, 10.0, 20.0, None),
        (None, None, None, None),
    ],
)
def test_ranges_conflict_any_missing_input_is_false(
    seed_lo: float | None, seed_hi: float | None, extracted_lo: float | None, extracted_hi: float | None
) -> None:
    from pescraper.merge import ranges_conflict

    assert ranges_conflict(seed_lo, seed_hi, extracted_lo, extracted_hi) is False


# --------------------------------------------------------------------------- #
# merge_firm_record
# --------------------------------------------------------------------------- #


def _make_record(**overrides):
    from pescraper.models import FirmRecord

    base = {"firm_name": "Acme Capital"}
    base.update(overrides)
    return FirmRecord(**base)


def test_merge_firm_record_brand_new_firm_passes_through_unchanged() -> None:
    from pescraper.merge import merge_firm_record

    new = _make_record(rev_min_musd=5.0)
    merged, conflicts = merge_firm_record(None, new)

    assert merged is new
    assert conflicts == []


def test_merge_firm_record_non_null_new_field_overwrites_existing() -> None:
    from pescraper.merge import merge_firm_record

    existing = _make_record(city="Chicago")
    new = _make_record(city="Boston")

    merged, conflicts = merge_firm_record(existing, new)

    assert merged.city == "Boston"
    assert conflicts == []


def test_merge_firm_record_null_new_field_never_clears_existing() -> None:
    from pescraper.merge import merge_firm_record

    existing = _make_record(city="Chicago")
    new = _make_record(city=None)

    merged, conflicts = merge_firm_record(existing, new)

    assert merged.city == "Chicago"


def test_merge_firm_record_lifecycle_fields_pass_through_from_existing() -> None:
    from pescraper.models import FirmStatus
    from pescraper.merge import merge_firm_record

    existing = _make_record(
        status=FirmStatus.COMPLETE,
        confidence=0.8,
        needs_review=False,
        last_checked="2026-01-01T00:00:00Z",
    )
    new = _make_record(
        status=FirmStatus.PENDING,
        confidence=0.1,
        needs_review=True,
        last_checked="2026-07-19T00:00:00Z",
    )

    merged, _ = merge_firm_record(existing, new)

    # Lifecycle fields are copied unchanged from existing — generic merge never
    # decides status/confidence/needs_review/last_checked; callers do that explicitly.
    assert merged.status == FirmStatus.COMPLETE
    assert merged.confidence == 0.8
    assert merged.needs_review is False
    assert merged.last_checked == "2026-01-01T00:00:00Z"


def test_merge_firm_record_no_conflict_when_ranges_overlap() -> None:
    from pescraper.merge import merge_firm_record

    existing = _make_record(ebitda_min_musd=5.0, ebitda_max_musd=25.0)
    new = _make_record(ebitda_min_musd=20.0, ebitda_max_musd=40.0)

    merged, conflicts = merge_firm_record(existing, new)

    assert conflicts == []
    # Non-null new values still win field-by-field even though ranges overlap.
    assert merged.ebitda_min_musd == 20.0
    assert merged.ebitda_max_musd == 40.0


def test_merge_firm_record_flags_conflict_for_each_disjoint_range_pair() -> None:
    from pescraper.merge import merge_firm_record

    existing = _make_record(
        rev_min_musd=5.0,
        rev_max_musd=10.0,
        ebitda_min_musd=5.0,
        ebitda_max_musd=10.0,
        ev_min_musd=5.0,
        ev_max_musd=10.0,
        check_min_musd=5.0,
        check_max_musd=10.0,
    )
    new = _make_record(
        rev_min_musd=100.0,
        rev_max_musd=200.0,
        ebitda_min_musd=100.0,
        ebitda_max_musd=200.0,
        ev_min_musd=100.0,
        ev_max_musd=200.0,
        check_min_musd=100.0,
        check_max_musd=200.0,
    )

    merged, conflicts = merge_firm_record(existing, new)

    assert set(conflicts) == {"rev", "ebitda", "ev", "check"}
    # Non-null new values still win despite the conflict flag.
    assert merged.rev_min_musd == 100.0


def test_merge_firm_record_missing_range_data_is_not_a_conflict() -> None:
    from pescraper.merge import merge_firm_record

    existing = _make_record(ebitda_min_musd=5.0, ebitda_max_musd=10.0)
    new = _make_record()  # no ebitda data at all

    merged, conflicts = merge_firm_record(existing, new)

    assert conflicts == []
    # null new never clears the existing confirmed range.
    assert merged.ebitda_min_musd == 5.0
    assert merged.ebitda_max_musd == 10.0
