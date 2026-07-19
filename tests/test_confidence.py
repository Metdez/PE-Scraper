from __future__ import annotations

from pescraper.confidence import compute_confidence, is_needs_review
from pescraper.models import FirmRecord


def test_compute_confidence_zero_populated() -> None:
    record = FirmRecord(firm_name="Acme Capital")
    assert compute_confidence(record) == 0.0


def test_compute_confidence_all_populated() -> None:
    record = FirmRecord(
        firm_name="Acme Capital",
        type="PE",
        state="CT",
        city="Greenwich",
        website="https://acme.example",
        us_investments=1,
        rev_min_musd=1.0,
        rev_max_musd=2.0,
        ebitda_min_musd=1.0,
        ebitda_max_musd=2.0,
        ev_min_musd=1.0,
        ev_max_musd=2.0,
        check_min_musd=1.0,
        check_max_musd=2.0,
        deal_types="Buyout",
        sector_tier1="Industrials",
        aum_musd=100.0,
        activity="Active",
    )
    assert compute_confidence(record) == 1.0


def test_compute_confidence_roughly_half() -> None:
    record = FirmRecord(
        firm_name="Acme Capital",
        type="PE",
        state="CT",
        city="Greenwich",
        website="https://acme.example",
        us_investments=1,
        rev_min_musd=1.0,
        rev_max_musd=2.0,
        ebitda_min_musd=1.0,
    )
    confidence = compute_confidence(record)
    assert 0.35 <= confidence <= 0.55


def test_is_needs_review_zero_core_numerics_overrides_ratio() -> None:
    record = FirmRecord(
        firm_name="Acme Capital",
        type="PE",
        state="CT",
        city="Greenwich",
        website="https://acme.example",
        us_investments=1,
        deal_types="Buyout",
        sector_tier1="Industrials",
    )
    assert is_needs_review(record, confidence=0.35) is True


def test_is_needs_review_below_threshold() -> None:
    record = FirmRecord(firm_name="Acme Capital", ebitda_min_musd=5.0)
    assert is_needs_review(record, confidence=0.1) is True


def test_is_needs_review_false_when_confident_and_has_core_numeric() -> None:
    record = FirmRecord(firm_name="Acme Capital", ebitda_min_musd=5.0)
    assert is_needs_review(record, confidence=0.5) is False
