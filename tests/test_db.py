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
