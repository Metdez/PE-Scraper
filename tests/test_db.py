"""Tests for the SQLite contract: FirmRecord model + db.py schema/lifecycle.

Structured so the plan's staged ``-k`` filters select the right cases:
- Task 1 (model/schema): ``-k "model or schema"``
- Task 2 (init/wal/columns/tables): ``-k "init or tables or wal or columns"``
- Task 3 (lifecycle/staleness): full-suite ``uv run pytest -q tests/test_db.py``

Each db-touching test uses pytest ``tmp_path`` for an isolated database file.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# --------------------------------------------------------------------------- #
# Task 1 — FirmRecord model + FIRM_COLUMNS (the 24-column contract)
# --------------------------------------------------------------------------- #


def test_firm_status_model_has_four_lifecycle_values() -> None:
    from pescraper.models import FirmStatus

    values = {s.value for s in FirmStatus}
    assert values == {"pending", "in_progress", "complete", "needs_review"}


def test_firm_record_schema_declares_24_columns_in_order() -> None:
    from pescraper.models import FIRM_COLUMNS, FirmRecord

    expected = (
        "firm_name",
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
        "last_deal",
        "fund_name",
        "confidence",
        "needs_review",
        "last_checked",
        "status",
    )
    # FIRM_COLUMNS is the single source of truth, in schema order.
    assert FIRM_COLUMNS == expected
    assert len(FIRM_COLUMNS) == 24
    # The pydantic model declares exactly those 24 fields, in the same order.
    assert tuple(FirmRecord.model_fields.keys()) == expected


def test_minimal_firm_record_model_validates_with_null_criteria() -> None:
    from pescraper.models import FirmRecord, FirmStatus

    record = FirmRecord(firm_name="Acme Capital")
    assert record.firm_name == "Acme Capital"
    # Every criteria field is null by default (Pitfall 1: no fabricated values).
    assert record.rev_min_musd is None
    assert record.ebitda_max_musd is None
    assert record.aum_musd is None
    assert record.deal_types is None
    # Non-null defaults.
    assert record.needs_review is False
    assert record.status is FirmStatus.PENDING

    # model_json_schema() round-trips: a JSON dump re-validates to an equal record.
    dumped = record.model_dump_json()
    assert FirmRecord.model_validate_json(dumped) == record


# --------------------------------------------------------------------------- #
# Task 2 — init_db idempotency, WAL, the five tables, firms columns
# --------------------------------------------------------------------------- #

FIVE_TABLES = {"jobs", "firms", "pages", "extractions", "cache"}


def test_init_db_creates_file_and_is_idempotent(tmp_path) -> None:
    from pescraper.db import init_db

    db_path = tmp_path / "pipeline.db"
    first = init_db(db_path)
    assert first.exists()
    # Second call is a no-op (CREATE TABLE IF NOT EXISTS) and returns the same path.
    second = init_db(db_path)
    assert second == first
    assert second.exists()


def test_init_db_enables_wal_journal_mode(tmp_path) -> None:
    from pescraper.db import connect, init_db

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert str(mode).lower() == "wal"


def test_init_db_creates_all_five_tables(tmp_path) -> None:
    from pescraper.db import connect, init_db

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    names = {r[0] for r in rows}
    assert FIVE_TABLES.issubset(names)


def test_firms_table_has_all_24_columns(tmp_path) -> None:
    from pescraper.db import connect, init_db
    from pescraper.models import FIRM_COLUMNS

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        info = conn.execute("PRAGMA table_info(firms)").fetchall()
    finally:
        conn.close()
    col_names = {row[1] for row in info}
    for name in FIRM_COLUMNS:
        assert name in col_names, f"firms table missing column {name!r}"


def test_connect_applies_busy_timeout_and_foreign_keys(tmp_path) -> None:
    from pescraper.db import connect, init_db

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        fks = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    finally:
        conn.close()
    assert int(busy) == 5000
    assert int(fks) == 1


# --------------------------------------------------------------------------- #
# Task 3 — status lifecycle + 90-day staleness query
# --------------------------------------------------------------------------- #


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_status_lifecycle_walk_and_rejects_disallowed(tmp_path) -> None:
    from pescraper.db import advance_status, connect, init_db, upsert_firm
    from pescraper.models import FirmRecord, FirmStatus

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        upsert_firm(
            conn,
            FirmRecord(firm_name="Acme Capital", website="https://acme.example"),
        )

        def current() -> str:
            return conn.execute(
                "SELECT status FROM firms WHERE website = ?",
                ("https://acme.example",),
            ).fetchone()[0]

        assert current() == FirmStatus.PENDING.value

        advance_status(conn, "https://acme.example", FirmStatus.IN_PROGRESS)
        assert current() == FirmStatus.IN_PROGRESS.value

        advance_status(conn, "https://acme.example", FirmStatus.COMPLETE)
        assert current() == FirmStatus.COMPLETE.value

        # complete is terminal — complete -> pending must raise.
        with pytest.raises(ValueError):
            advance_status(conn, "https://acme.example", FirmStatus.PENDING)
    finally:
        conn.close()


def test_stale_firms_surfaces_old_and_never_checked(tmp_path) -> None:
    from pescraper.db import connect, init_db, stale_firms, upsert_firm
    from pescraper.models import FirmRecord

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        upsert_firm(
            conn,
            FirmRecord(
                firm_name="Old Firm",
                website="https://old.example",
                last_checked=_iso_days_ago(100),
            ),
        )
        upsert_firm(
            conn,
            FirmRecord(
                firm_name="Recent Firm",
                website="https://recent.example",
                last_checked=_iso_days_ago(10),
            ),
        )
        upsert_firm(
            conn,
            FirmRecord(firm_name="Never Firm", website="https://never.example"),
        )

        stale = set(stale_firms(conn, days=90))
        assert "https://old.example" in stale
        assert "https://never.example" in stale
        assert "https://recent.example" not in stale
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Task 1 (02-02) — get_firm: read a FirmRecord back by website
# --------------------------------------------------------------------------- #


def test_get_firm_returns_none_for_missing_website(tmp_path) -> None:
    from pescraper.db import connect, get_firm, init_db

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        assert get_firm(conn, "https://no-such-firm.example") is None
    finally:
        conn.close()


def test_get_firm_round_trips_fully_populated_record(tmp_path) -> None:
    from pescraper.db import connect, get_firm, init_db, upsert_firm
    from pescraper.models import FirmRecord, FirmStatus

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        record = FirmRecord(
            firm_name="Acme Capital",
            type="Buyout",
            state="NY",
            city="New York",
            website="https://acme.example",
            us_investments=42,
            rev_min_musd=10.0,
            rev_max_musd=100.0,
            ebitda_min_musd=2.0,
            ebitda_max_musd=20.0,
            ev_min_musd=5.0,
            ev_max_musd=50.0,
            check_min_musd=1.0,
            check_max_musd=25.0,
            deal_types="Buyout,Growth Equity",
            sector_tier1="Industrials",
            aum_musd=500.0,
            activity="Active",
            last_deal="2026-01-01",
            fund_name="Acme Fund III",
            confidence=0.85,
            needs_review=True,
            last_checked="2026-07-19T00:00:00+00:00",
            status=FirmStatus.NEEDS_REVIEW,
        )
        upsert_firm(conn, record)

        result = get_firm(conn, "https://acme.example")
        assert result == record
        assert isinstance(result.status, FirmStatus)
        assert isinstance(result.needs_review, bool)
    finally:
        conn.close()


def test_get_firm_round_trips_minimal_record_nulls_stay_none(tmp_path) -> None:
    from pescraper.db import connect, get_firm, init_db, upsert_firm
    from pescraper.models import FirmRecord, FirmStatus

    db_path = tmp_path / "pipeline.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        record = FirmRecord(firm_name="Minimal Firm", website="https://minimal.example")
        upsert_firm(conn, record)

        result = get_firm(conn, "https://minimal.example")
        assert result == record
        assert result.rev_min_musd is None
        assert result.ebitda_max_musd is None
        assert result.deal_types is None
        assert result.needs_review is False
        assert result.status is FirmStatus.PENDING
    finally:
        conn.close()
