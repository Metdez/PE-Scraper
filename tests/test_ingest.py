from __future__ import annotations

from pescraper.ingest import ingest_csv, parse_range, row_to_firm_record
from pescraper.models import FirmRecord


def test_parse_range_dollar_million() -> None:
    assert parse_range("$5-25M") == (5.0, 25.0)


def test_parse_range_with_to_word() -> None:
    assert parse_range("5 to 25") == (5.0, 25.0)


def test_parse_range_billion_scales_to_millions() -> None:
    assert parse_range("$1-2B") == (1000.0, 2000.0)


def test_parse_range_blank_cell_returns_none_none() -> None:
    assert parse_range("") == (None, None)
    assert parse_range(None) == (None, None)


def test_parse_range_unparseable_cell_returns_none_none() -> None:
    assert parse_range("call for details") == (None, None)


def test_row_to_firm_record_maps_direct_columns_case_insensitively() -> None:
    row = {
        "Firm Name": "A&M Capital Advisors, LP",
        "TYPE": "PE",
        "State": "CT",
        "city": "Greenwich",
        "Website": "https://www.a-mcapital.com",
        "Rev Min ($M)": "15.0",
        "Rev Max ($M)": "100.0",
        "EBITDA Min ($M)": "75.0",
        "EBITDA Max ($M)": "750.0",
        "Deal Types": "Buyout, Recap, Other",
        "Sector Tier 1": "Business Services, Healthcare, Industrials",
        "AUM ($M)": "5900.0",
        "Activity": "Active",
    }
    record = row_to_firm_record(row)
    assert isinstance(record, FirmRecord)
    assert record.firm_name == "A&M Capital Advisors, LP"
    assert record.type == "PE"
    assert record.state == "CT"
    assert record.city == "Greenwich"
    assert record.rev_min_musd == 15.0
    assert record.rev_max_musd == 100.0
    assert record.ebitda_min_musd == 75.0
    assert record.ebitda_max_musd == 750.0
    assert record.aum_musd == 5900.0


def test_row_to_firm_record_parses_free_text_range_column() -> None:
    row = {"Firm Name": "Acme Capital", "EBITDA Range": "$5-25M"}
    record = row_to_firm_record(row)
    assert record.ebitda_min_musd == 5.0
    assert record.ebitda_max_musd == 25.0


def test_row_to_firm_record_direct_column_takes_priority_over_range_column() -> None:
    row = {
        "Firm Name": "Acme Capital",
        "EBITDA Min ($M)": "10.0",
        "EBITDA Range": "$5-25M",
    }
    record = row_to_firm_record(row)
    assert record.ebitda_min_musd == 10.0


def test_row_to_firm_record_clean_numeric_cell_is_noop_passthrough() -> None:
    row = {"Firm Name": "Acme Capital", "EBITDA Min ($M)": "5.0"}
    record = row_to_firm_record(row)
    assert record.ebitda_min_musd == 5.0


def test_row_to_firm_record_missing_firm_name_returns_none() -> None:
    row = {"Type": "PE", "State": "CT"}
    assert row_to_firm_record(row) is None


def test_row_to_firm_record_blank_firm_name_returns_none() -> None:
    row = {"Firm Name": "   ", "Type": "PE"}
    assert row_to_firm_record(row) is None


def test_ingest_csv_reads_file_and_skips_unusable_rows(tmp_path) -> None:
    csv_path = tmp_path / "firms.csv"
    csv_path.write_text(
        "Firm Name,Type,State,Rev Min ($M),Rev Max ($M),EBITDA Range\n"
        '"A&M Capital Advisors, LP",PE,CT,15.0,100.0,\n'
        ",PE,FL,,,\n"
        "Agellus Capital LLC,PE,,,,$2-25M\n",
        encoding="utf-8",
    )
    records = ingest_csv(csv_path)
    assert len(records) == 2
    names = {r.firm_name for r in records}
    assert "A&M Capital Advisors, LP" in names
    agellus = next(r for r in records if r.firm_name == "Agellus Capital LLC")
    assert agellus.ebitda_min_musd == 2.0
    assert agellus.ebitda_max_musd == 25.0
