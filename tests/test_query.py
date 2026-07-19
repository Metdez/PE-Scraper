from __future__ import annotations

from pescraper.models import FirmRecord
from pescraper.query import find_firms

FIRMS = [
    FirmRecord(
        firm_name="Industrial Buyouts LLC",
        state="CT",
        sector_tier1="Industrials, Business Services",
        deal_types="Buyout",
        ebitda_min_musd=5.0,
        ebitda_max_musd=25.0,
    ),
    FirmRecord(
        firm_name="Healthcare Growth Partners",
        state="NY",
        sector_tier1="Healthcare",
        deal_types="Growth Equity",
        ebitda_min_musd=50.0,
        ebitda_max_musd=200.0,
    ),
    FirmRecord(firm_name="No Data Firm"),
]


def test_find_by_state() -> None:
    assert [r.firm_name for r in find_firms(FIRMS, state="CT")] == ["Industrial Buyouts LLC"]


def test_find_by_sector_substring() -> None:
    results = find_firms(FIRMS, sector="Industrials")
    assert len(results) == 1
    assert results[0].firm_name == "Industrial Buyouts LLC"


def test_find_by_deal_type_and_ebitda_overlap() -> None:
    results = find_firms(FIRMS, deal_type="Buyout", ebitda_min=5, ebitda_max=25)
    assert len(results) == 1
    assert results[0].firm_name == "Industrial Buyouts LLC"


def test_find_ebitda_range_excludes_non_overlapping_firm() -> None:
    results = find_firms(FIRMS, ebitda_min=5, ebitda_max=25)
    names = {r.firm_name for r in results}
    assert names == {"Industrial Buyouts LLC"}


def test_find_excludes_firms_with_no_data_when_range_filter_applied() -> None:
    results = find_firms(FIRMS, ebitda_min=0, ebitda_max=1000)
    names = {r.firm_name for r in results}
    assert "No Data Firm" not in names


def test_find_no_filters_returns_everything() -> None:
    assert len(find_firms(FIRMS)) == 3
