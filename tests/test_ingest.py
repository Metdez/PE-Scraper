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
