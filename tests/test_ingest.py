"""Tests for pescraper.ingest — Capital IQ CSV seed ingest.

Covers Task 1 (column mapper + free-text range regex parser, pure functions,
no I/O) and Task 2 (ingest_csv orchestrator, seeds pipeline.db via merge.py's
universal null-safe merge rule). See
.planning/phases/02-core-pipeline-single-firm/02-05-PLAN.md and 02-CONTEXT.md
"Capital IQ Seeding & Merge Rules".

Staged ``-k`` filters:
- Task 1: ``uv run pytest tests/test_ingest.py -k "parse_range or map_columns" -x -q``
- Task 2 (full suite): ``uv run pytest tests/test_ingest.py -x -q``
"""

from __future__ import annotations

import csv
import sqlite3

import pytest


# --------------------------------------------------------------------------- #
# Task 1a — parse_range
# --------------------------------------------------------------------------- #


def test_parse_range_simple_dollar_range_with_million_suffix() -> None:
    from pescraper.ingest import parse_range

    assert parse_range("$5-25M") == (5.0, 25.0)


def test_parse_range_billion_range_converts_to_millions() -> None:
    from pescraper.ingest import parse_range

    assert parse_range("$1.5B - $2B") == (1500.0, 2000.0)


def test_parse_range_word_separator_to() -> None:
    from pescraper.ingest import parse_range

    assert parse_range("5 to 25") == (5.0, 25.0)


def test_parse_range_bare_single_number_is_both_min_and_max() -> None:
    """Documented Claude's-discretion behavior (per PLAN.md Task 1 action):

    a bare number with no range separator is treated as both min and max —
    a single confirmed figure is still a confirmed data point, not a range.
    """
    from pescraper.ingest import parse_range

    assert parse_range("15") == (15.0, 15.0)


def test_parse_range_clean_numeric_cell_is_not_mangled() -> None:
    """An already-clean numeric CSV cell passes through as a no-op, not mangled."""
    from pescraper.ingest import parse_range

    assert parse_range("25.0") == (25.0, 25.0)


def test_parse_range_empty_string_is_none_none() -> None:
    from pescraper.ingest import parse_range

    assert parse_range("") == (None, None)


def test_parse_range_none_input_is_none_none() -> None:
    from pescraper.ingest import parse_range

    assert parse_range(None) == (None, None)


def test_parse_range_whitespace_only_is_none_none() -> None:
    from pescraper.ingest import parse_range

    assert parse_range("   ") == (None, None)


def test_parse_range_no_numbers_at_all_is_none_none() -> None:
    from pescraper.ingest import parse_range

    assert parse_range("undisclosed") == (None, None)


# --------------------------------------------------------------------------- #
# Task 1b — map_columns / COLUMN_ALIASES
# --------------------------------------------------------------------------- #


def test_map_columns_maps_known_aliases_case_insensitively() -> None:
    from pescraper.ingest import map_columns

    mapping = map_columns(["Firm Name", "EBITDA Range", "Website"])

    assert mapping["Firm Name"] == "firm_name"
    assert mapping["EBITDA Range"] == "_ebitda_range"
    assert mapping["Website"] == "website"


def test_map_columns_unrecognized_header_passes_through_lowercased_stripped() -> None:
    from pescraper.ingest import map_columns

    mapping = map_columns([" Some Weird Column "])

    assert mapping[" Some Weird Column "] == "some weird column"


def test_map_columns_covers_identity_and_range_aliases() -> None:
    from pescraper.ingest import map_columns

    mapping = map_columns(
        [
            "Firm",
            "State",
            "City",
            "Type",
            "Sector",
            "Deal Types",
            "AUM",
            "Rev Range",
            "EV Range",
            "Check Size",
        ]
    )

    assert mapping["Firm"] == "firm_name"
    assert mapping["State"] == "state"
    assert mapping["City"] == "city"
    assert mapping["Type"] == "type"
    assert mapping["Sector"] == "sector_tier1"
    assert mapping["Deal Types"] == "deal_types"
    assert mapping["AUM"] == "aum_musd"
    assert mapping["Rev Range"] == "_rev_range"
    assert mapping["EV Range"] == "_ev_range"
    assert mapping["Check Size"] == "_check_range"


def test_map_columns_covers_capital_iq_export_aliases() -> None:
    from pescraper.ingest import map_columns

    mapping = map_columns(["Entity Name", "Web Address", "Sector Emphasis"])

    assert mapping["Entity Name"] == "firm_name"
    assert mapping["Web Address"] == "_capiq_website"
    assert mapping["Sector Emphasis"] == "sector_tier1"


def test_map_columns_collapses_embedded_newline_headers() -> None:
    """Capital IQ wraps a column's unit onto a second physical line inside the
    header cell itself -- map_columns must collapse that whitespace (including
    the newline) before the alias lookup so these headers resolve correctly."""
    from pescraper.ingest import map_columns

    mapping = map_columns(
        ["Assets Under Management\n($000)", "Total Investments\n(actual)"]
    )

    assert mapping["Assets Under Management\n($000)"] == "_capiq_aum_thousands"
    assert mapping["Total Investments\n(actual)"] == "us_investments"


# --------------------------------------------------------------------------- #
# Task 2 — ingest_csv
# --------------------------------------------------------------------------- #


def _write_csv(path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _connect(tmp_path) -> sqlite3.Connection:
    from pescraper import db

    db_path = tmp_path / "pipeline.db"
    db.init_db(db_path)
    return db.connect(db_path)


def test_ingest_csv_inserts_two_new_firms_with_parsed_ranges(tmp_path) -> None:
    from pescraper import db
    from pescraper.ingest import ingest_csv
    from pescraper.models import FirmStatus

    csv_path = tmp_path / "seed.csv"
    _write_csv(
        csv_path,
        [
            {
                "Firm Name": "Acme Capital",
                "Website": "acme.example",
                "EBITDA Range": "$5-25M",
            },
            {
                "Firm Name": "Beta Partners",
                "Website": "beta.example",
                "EBITDA Range": "$10-50M",
            },
        ],
        fieldnames=["Firm Name", "Website", "EBITDA Range"],
    )

    conn = _connect(tmp_path)
    summary = ingest_csv(csv_path, conn)

    assert summary.rows_read == 2
    assert summary.rows_seeded == 2
    assert summary.rows_skipped == 0

    acme = db.get_firm(conn, "acme.example")
    assert acme is not None
    assert acme.ebitda_min_musd == 5.0
    assert acme.ebitda_max_musd == 25.0
    assert acme.status == FirmStatus.PENDING

    beta = db.get_firm(conn, "beta.example")
    assert beta is not None
    assert beta.ebitda_min_musd == 10.0
    assert beta.ebitda_max_musd == 50.0


def test_ingest_csv_supports_capital_iq_identity_headers_and_normalizes_website(tmp_path) -> None:
    from pescraper import db
    from pescraper.ingest import ingest_csv

    csv_path = tmp_path / "capiq.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Entity Name", "Web Address", "Sector Emphasis"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Entity Name": "Acme Capital",
                "Web Address": "www.acme.example",
                "Sector Emphasis": "Industrials",
            }
        )

    conn = _connect(tmp_path)
    summary = ingest_csv(csv_path, conn)

    assert summary.rows_read == 1
    assert summary.rows_seeded == 1
    assert summary.rows_skipped == 0

    acme = db.get_firm(conn, "https://www.acme.example")
    assert acme is not None
    assert acme.firm_name == "Acme Capital"
    assert acme.sector_tier1 == "Industrials"


def test_ingest_csv_preserves_complete_status_not_reset_to_pending(tmp_path) -> None:
    from pescraper import db
    from pescraper.ingest import ingest_csv
    from pescraper.models import FirmRecord, FirmStatus

    conn = _connect(tmp_path)
    db.upsert_firm(
        conn,
        FirmRecord(
            firm_name="Acme Capital",
            website="acme.example",
            status=FirmStatus.COMPLETE,
            confidence=0.9,
        ),
    )

    csv_path = tmp_path / "seed.csv"
    _write_csv(
        csv_path,
        [{"Firm Name": "Acme Capital", "Website": "acme.example", "EBITDA Range": "$5-25M"}],
        fieldnames=["Firm Name", "Website", "EBITDA Range"],
    )

    summary = ingest_csv(csv_path, conn)

    assert summary.rows_seeded == 1
    acme = db.get_firm(conn, "acme.example")
    assert acme is not None
    assert acme.status == FirmStatus.COMPLETE
    assert acme.confidence == 0.9


def test_ingest_csv_flags_needs_review_on_disjoint_range_conflict(tmp_path) -> None:
    from pescraper import db
    from pescraper.ingest import ingest_csv
    from pescraper.models import FirmRecord, FirmStatus

    conn = _connect(tmp_path)
    db.upsert_firm(
        conn,
        FirmRecord(
            firm_name="Acme Capital",
            website="acme.example",
            status=FirmStatus.COMPLETE,
            ebitda_min_musd=5.0,
            ebitda_max_musd=10.0,
        ),
    )

    csv_path = tmp_path / "seed.csv"
    _write_csv(
        csv_path,
        [{"Firm Name": "Acme Capital", "Website": "acme.example", "EBITDA Range": "$100-200M"}],
        fieldnames=["Firm Name", "Website", "EBITDA Range"],
    )

    summary = ingest_csv(csv_path, conn)

    assert summary.rows_conflicted == 1
    acme = db.get_firm(conn, "acme.example")
    assert acme is not None
    assert acme.needs_review is True


def test_ingest_csv_skips_row_missing_both_firm_name_and_website(tmp_path) -> None:
    from pescraper.ingest import ingest_csv

    csv_path = tmp_path / "seed.csv"
    _write_csv(
        csv_path,
        [
            {"Firm Name": "", "Website": "", "EBITDA Range": "$5-25M"},
            {"Firm Name": "Beta Partners", "Website": "beta.example", "EBITDA Range": ""},
        ],
        fieldnames=["Firm Name", "Website", "EBITDA Range"],
    )

    conn = _connect(tmp_path)
    summary = ingest_csv(csv_path, conn)

    assert summary.rows_read == 2
    assert summary.rows_skipped == 1
    assert summary.rows_seeded == 1


def test_ingest_csv_clean_numeric_min_max_columns_take_precedence_over_range_column(
    tmp_path,
) -> None:
    """A row with clean numeric *_min_musd/*_max_musd columns bypasses regex parsing."""
    from pescraper import db
    from pescraper.ingest import ingest_csv

    csv_path = tmp_path / "seed.csv"
    _write_csv(
        csv_path,
        [
            {
                "Firm Name": "Acme Capital",
                "Website": "acme.example",
                "ebitda_min_musd": "7",
                "ebitda_max_musd": "30",
                "EBITDA Range": "$5-25M",
            }
        ],
        fieldnames=["Firm Name", "Website", "ebitda_min_musd", "ebitda_max_musd", "EBITDA Range"],
    )

    conn = _connect(tmp_path)
    ingest_csv(csv_path, conn)

    acme = db.get_firm(conn, "acme.example")
    assert acme is not None
    assert acme.ebitda_min_musd == 7.0
    assert acme.ebitda_max_musd == 30.0


def test_ingest_csv_converts_capiq_aum_thousands_to_musd(tmp_path) -> None:
    """A Capital IQ AUM cell denominated in $000s converts to the $M scale
    FirmRecord.aum_musd expects: "1,200,000.00" -> 1200.0."""
    from pescraper import db
    from pescraper.ingest import ingest_csv

    csv_path = tmp_path / "capiq.csv"
    _write_csv(
        csv_path,
        [
            {
                "Entity Name": "TR Advisors Ltd",
                "Web Address": "www.tr-capital.com",
                "Assets Under Management\n($000)": "1,200,000.00",
            }
        ],
        fieldnames=["Entity Name", "Web Address", "Assets Under Management\n($000)"],
    )

    conn = _connect(tmp_path)
    ingest_csv(csv_path, conn)

    tr = db.get_firm(conn, "https://www.tr-capital.com")
    assert tr is not None
    assert tr.aum_musd == 1200.0


def test_ingest_csv_treats_na_as_missing_for_direct_numeric_field(tmp_path) -> None:
    """A literal "NA" cell in a direct FirmRecord field becomes null rather
    than raising a Pydantic validation error and skipping the whole row."""
    from pescraper import db
    from pescraper.ingest import ingest_csv

    csv_path = tmp_path / "capiq.csv"
    _write_csv(
        csv_path,
        [
            {
                "Entity Name": "Acme Capital",
                "Web Address": "www.acme.example",
                "Total Investments\n(actual)": "NA",
            }
        ],
        fieldnames=["Entity Name", "Web Address", "Total Investments\n(actual)"],
    )

    conn = _connect(tmp_path)
    summary = ingest_csv(csv_path, conn)

    assert summary.rows_skipped == 0
    assert summary.rows_seeded == 1

    acme = db.get_firm(conn, "https://www.acme.example")
    assert acme is not None
    assert acme.us_investments is None


def test_ingest_csv_strips_thousands_separator_commas_from_numeric_direct_field(
    tmp_path,
) -> None:
    """Capital IQ emits thousands-separator commas in some integer columns
    (e.g. "1,238"), which Pydantic's int coercion cannot parse directly --
    ingest_csv must strip them before constructing FirmRecord."""
    from pescraper import db
    from pescraper.ingest import ingest_csv

    csv_path = tmp_path / "capiq.csv"
    _write_csv(
        csv_path,
        [
            {
                "Entity Name": "Acme Capital",
                "Web Address": "www.acme.example",
                "Total Investments\n(actual)": "1,238",
            }
        ],
        fieldnames=["Entity Name", "Web Address", "Total Investments\n(actual)"],
    )

    conn = _connect(tmp_path)
    summary = ingest_csv(csv_path, conn)

    assert summary.rows_skipped == 0
    acme = db.get_firm(conn, "https://www.acme.example")
    assert acme is not None
    assert acme.us_investments == 1238


def test_ingest_csv_maps_total_investments_actual_to_us_investments(tmp_path) -> None:
    """A populated "Total Investments\n(actual)" cell maps to us_investments."""
    from pescraper import db
    from pescraper.ingest import ingest_csv

    csv_path = tmp_path / "capiq.csv"
    _write_csv(
        csv_path,
        [
            {
                "Entity Name": "Acme Capital",
                "Web Address": "www.acme.example",
                "Total Investments\n(actual)": "49",
            }
        ],
        fieldnames=["Entity Name", "Web Address", "Total Investments\n(actual)"],
    )

    conn = _connect(tmp_path)
    ingest_csv(csv_path, conn)

    acme = db.get_firm(conn, "https://www.acme.example")
    assert acme is not None
    assert acme.us_investments == 49


def test_ingest_csv_never_writes_fund_status_to_status_field(tmp_path) -> None:
    """A "Fund Status" column with an arbitrary non-empty value never reaches
    FirmRecord.status -- it stays unmapped and the firm keeps FirmStatus.PENDING."""
    from pescraper import db
    from pescraper.ingest import ingest_csv
    from pescraper.models import FirmStatus

    csv_path = tmp_path / "capiq.csv"
    _write_csv(
        csv_path,
        [
            {
                "Entity Name": "Acme Capital",
                "Web Address": "www.acme.example",
                "Fund Status": "Raising Fund IV",
            }
        ],
        fieldnames=["Entity Name", "Web Address", "Fund Status"],
    )

    conn = _connect(tmp_path)
    ingest_csv(csv_path, conn)

    acme = db.get_firm(conn, "https://www.acme.example")
    assert acme is not None
    assert acme.status == FirmStatus.PENDING


def test_ingest_csv_real_capital_iq_header_shape_all_fields_resolve_together(
    tmp_path,
) -> None:
    """One combined row using all 12 real header columns from
    data/capiq_test.csv, modeled on the file's actual "Borgman Capital LLC"
    row -- confirms every new/existing alias and coercion resolves together."""
    from pescraper import db
    from pescraper.ingest import ingest_csv
    from pescraper.models import FirmStatus

    fieldnames = [
        "Entity Name",
        "Entity ID",
        "Web Address",
        "Year Incorporated",
        "Assets Under Management\n($000)",
        "Number of Company Employees\n(actual)",
        "Total Investments\n(actual)",
        "Total Active Investments\n(actual)",
        "Total LTM Investments\n(actual)",
        "Sector Emphasis",
        "Market Cap Emphasis",
        "Fund Status",
    ]
    csv_path = tmp_path / "capiq_real_shape.csv"
    _write_csv(
        csv_path,
        [
            {
                "Entity Name": "Borgman Capital LLC",
                "Entity ID": "10008676",
                "Web Address": "www.borgmancapital.com",
                "Year Incorporated": "2017",
                "Assets Under Management\n($000)": "NA",
                "Number of Company Employees\n(actual)": "NA",
                "Total Investments\n(actual)": "19",
                "Total Active Investments\n(actual)": "8",
                "Total LTM Investments\n(actual)": "2",
                "Sector Emphasis": "Industrials",
                "Market Cap Emphasis": "",
                "Fund Status": "",
            }
        ],
        fieldnames=fieldnames,
    )

    conn = _connect(tmp_path)
    ingest_csv(csv_path, conn)

    borgman = db.get_firm(conn, "https://www.borgmancapital.com")
    assert borgman is not None
    assert borgman.firm_name == "Borgman Capital LLC"
    assert borgman.website == "https://www.borgmancapital.com"
    assert borgman.sector_tier1 == "Industrials"
    assert borgman.us_investments == 19
    assert borgman.aum_musd is None
    assert borgman.status == FirmStatus.PENDING
