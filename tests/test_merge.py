from __future__ import annotations

from pescraper.merge import merge_field, merge_firm_record, ranges_conflict
from pescraper.models import FirmRecord, FirmStatus


def test_merge_field_new_wins_when_non_null() -> None:
    assert merge_field(5.0, 25.0) == 25.0


def test_merge_field_null_never_clears() -> None:
    assert merge_field(5.0, None) == 5.0


def test_merge_field_both_null() -> None:
    assert merge_field(None, None) is None


def test_ranges_conflict_disjoint() -> None:
    assert ranges_conflict(5.0, 10.0, 20.0, 30.0) is True


def test_ranges_conflict_overlapping_is_not_conflict() -> None:
    assert ranges_conflict(5.0, 20.0, 10.0, 30.0) is False


def test_ranges_conflict_nested_is_not_conflict() -> None:
    assert ranges_conflict(5.0, 30.0, 10.0, 20.0) is False


def test_ranges_conflict_missing_data_is_not_conflict() -> None:
    assert ranges_conflict(None, 10.0, 5.0, 20.0) is False
    assert ranges_conflict(5.0, None, None, None) is False


def test_merge_firm_record_first_time_firm_passthrough() -> None:
    new = FirmRecord(firm_name="Acme Capital")
    merged, conflicts = merge_firm_record(None, new)
    assert merged is new
    assert conflicts == []


def test_merge_firm_record_lifecycle_fields_pass_through_from_existing() -> None:
    existing = FirmRecord(
        firm_name="Acme Capital",
        confidence=0.9,
        needs_review=False,
        last_checked="2026-01-01T00:00:00+00:00",
        status=FirmStatus.COMPLETE,
    )
    new = FirmRecord(
        firm_name="Acme Capital",
        confidence=0.1,
        needs_review=True,
        last_checked="2026-06-01T00:00:00+00:00",
        status=FirmStatus.PENDING,
    )
    merged, _ = merge_firm_record(existing, new)
    assert merged.confidence == 0.9
    assert merged.needs_review is False
    assert merged.last_checked == "2026-01-01T00:00:00+00:00"
    assert merged.status == FirmStatus.COMPLETE


def test_merge_firm_record_non_null_wins_over_confirmed_value() -> None:
    existing = FirmRecord(firm_name="Acme Capital", city="Boston")
    new = FirmRecord(firm_name="Acme Capital", city="New York")
    merged, _ = merge_firm_record(existing, new)
    assert merged.city == "New York"


def test_merge_firm_record_null_never_clears_existing() -> None:
    existing = FirmRecord(firm_name="Acme Capital", city="Boston")
    new = FirmRecord(firm_name="Acme Capital", city=None)
    merged, _ = merge_firm_record(existing, new)
    assert merged.city == "Boston"


def test_merge_firm_record_detects_conflict_for_all_range_pairs() -> None:
    existing = FirmRecord(
        firm_name="Acme Capital",
        rev_min_musd=1.0,
        rev_max_musd=5.0,
        ebitda_min_musd=1.0,
        ebitda_max_musd=5.0,
        ev_min_musd=1.0,
        ev_max_musd=5.0,
        check_min_musd=1.0,
        check_max_musd=5.0,
    )
    new = FirmRecord(
        firm_name="Acme Capital",
        rev_min_musd=100.0,
        rev_max_musd=200.0,
        ebitda_min_musd=100.0,
        ebitda_max_musd=200.0,
        ev_min_musd=100.0,
        ev_max_musd=200.0,
        check_min_musd=100.0,
        check_max_musd=200.0,
    )
    _, conflicts = merge_firm_record(existing, new)
    assert set(conflicts) == {"rev", "ebitda", "ev", "check"}


def test_merge_firm_record_no_conflict_when_ranges_agree() -> None:
    existing = FirmRecord(firm_name="Acme Capital", ebitda_min_musd=5.0, ebitda_max_musd=25.0)
    new = FirmRecord(firm_name="Acme Capital", ebitda_min_musd=10.0, ebitda_max_musd=20.0)
    _, conflicts = merge_firm_record(existing, new)
    assert conflicts == []
