"""Deterministic dataset lookup functions for CLI and chat adapters."""

from __future__ import annotations

import sqlite3

from pescraper.models import FirmRecord, FirmStatus


def _record(row: sqlite3.Row) -> FirmRecord:
    data = dict(row)
    data["needs_review"] = bool(data["needs_review"])
    data["status"] = FirmStatus(data["status"])
    return FirmRecord(**data)


def find_firm(conn: sqlite3.Connection, name_or_url: str) -> FirmRecord | None:
    row = conn.execute(
        "SELECT * FROM firms WHERE website = ? OR firm_name LIKE ? ORDER BY firm_name LIMIT 1",
        (name_or_url, f"%{name_or_url}%"),
    ).fetchone()
    return _record(row) if row else None


def search_firms(
    conn: sqlite3.Connection,
    *,
    ebitda_min: float | None = None,
    ebitda_max: float | None = None,
    deal_type: str | None = None,
    sector: str | None = None,
    limit: int = 50,
) -> list[FirmRecord]:
    clauses: list[str] = []
    params: list[object] = []
    if ebitda_min is not None:
        clauses.append("ebitda_min_musd <= ?")
        params.append(ebitda_min)
    if ebitda_max is not None:
        clauses.append("ebitda_max_musd >= ?")
        params.append(ebitda_max)
    if deal_type:
        clauses.append("LOWER(deal_types) LIKE ?")
        params.append(f"%{deal_type.casefold()}%")
    if sector:
        clauses.append("LOWER(sector_tier1) LIKE ?")
        params.append(f"%{sector.casefold()}%")
    where = " AND ".join(clauses) if clauses else "1=1"
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM firms WHERE {where} ORDER BY firm_name LIMIT ?",
        params,
    ).fetchall()
    return [_record(row) for row in rows]


def format_firm(record: FirmRecord) -> str:
    values = record.model_dump(mode="json")
    populated = [f"{name}: {value}" for name, value in values.items() if value is not None]
    return "\n".join(populated)


__all__ = ["find_firm", "format_firm", "search_firms"]
