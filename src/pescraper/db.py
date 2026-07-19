"""SQLite contract for the pipeline — ``pipeline.db``, the source of truth.

Per ARCHITECTURE.md ("two halves, one contract") this is the ONLY module that
writes SQL. The five tables (jobs, firms, pages, extractions, cache) are the
inter-phase / inter-language contract every later phase reads and writes.

Design invariants (PITFALLS Pitfall 7 & 10):
- WAL journal mode + ``busy_timeout`` on every connection so the batch worker and
  interactive "research this firm" requests can touch the DB concurrently without
  ``SQLITE_BUSY`` corruption.
- Per-call commits keep writes atomic and crash-safe (a killed process never loses
  more than the row in flight).
- The ``firms`` DDL is generated from :data:`pescraper.models.FIRM_COLUMNS`, so the
  SQLite shape and the pydantic/Ollama shape are one contract.

Only the ``firms`` table is fully specified this phase; jobs/pages/extractions/cache
are skeleton tables (later phases extend their columns) but must EXIST now as part
of the contract.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from pescraper.models import FIRM_COLUMNS, FirmRecord, FirmStatus

# Default DB path: env override (PESCRAPER_DB) else data/pipeline.db under cwd.
DEFAULT_DB_PATH: Path = Path(os.environ.get("PESCRAPER_DB", "data/pipeline.db"))

# SQLite column type per firms field. website is the natural key (see DDL below).
_FIRM_COLUMN_TYPES: dict[str, str] = {
    "firm_name": "TEXT NOT NULL",
    "type": "TEXT",
    "state": "TEXT",
    "city": "TEXT",
    "website": "TEXT",
    "us_investments": "INTEGER",
    "rev_min_musd": "REAL",
    "rev_max_musd": "REAL",
    "ebitda_min_musd": "REAL",
    "ebitda_max_musd": "REAL",
    "ev_min_musd": "REAL",
    "ev_max_musd": "REAL",
    "check_min_musd": "REAL",
    "check_max_musd": "REAL",
    "deal_types": "TEXT",
    "sector_tier1": "TEXT",
    "aum_musd": "REAL",
    "activity": "TEXT",
    "last_deal": "TEXT",
    "fund_name": "TEXT",
    "confidence": "REAL",
    "needs_review": "INTEGER NOT NULL DEFAULT 0",
    "last_checked": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'pending'",
}

# Status lifecycle: pending -> in_progress -> {complete | needs_review}.
# Terminal states (complete, needs_review) have no outgoing transitions.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    FirmStatus.PENDING.value: frozenset({FirmStatus.IN_PROGRESS.value}),
    FirmStatus.IN_PROGRESS.value: frozenset(
        {FirmStatus.COMPLETE.value, FirmStatus.NEEDS_REVIEW.value}
    ),
    FirmStatus.COMPLETE.value: frozenset(),
    FirmStatus.NEEDS_REVIEW.value: frozenset(),
}


def _firms_ddl() -> str:
    """Build the firms CREATE TABLE from FIRM_COLUMNS (single source of truth).

    An implicit integer ``rowid`` primary key backs the table; the 24 named schema
    columns are exactly FIRM_COLUMNS. ``website`` carries a UNIQUE constraint so it
    can serve as the natural key for upserts and lifecycle updates.
    """
    col_defs = [f"    {name} {_FIRM_COLUMN_TYPES[name]}" for name in FIRM_COLUMNS]
    col_defs.append("    UNIQUE(website)")
    body = ",\n".join(col_defs)
    return f"CREATE TABLE IF NOT EXISTS firms (\n{body}\n)"


# Skeleton tables — columns later phases extend, but they must exist now.
_SKELETON_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY,
        kind TEXT,
        payload TEXT,
        priority INTEGER DEFAULT 9,
        status TEXT DEFAULT 'queued',
        attempts INTEGER DEFAULT 0,
        claimed_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY,
        firm_website TEXT,
        url TEXT,
        fetched_at TEXT,
        content_hash TEXT,
        fit_markdown TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS extractions (
        id INTEGER PRIMARY KEY,
        firm_website TEXT,
        source_page_url TEXT,
        field TEXT,
        value TEXT,
        quote TEXT,
        model TEXT,
        prompt_version TEXT,
        content_hash TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cache (
        cache_key TEXT PRIMARY KEY,
        kind TEXT,
        content_hash TEXT,
        prompt_version TEXT,
        model TEXT,
        value TEXT,
        created_at TEXT
    )
    """,
)

_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_firms_status ON firms(status)",
    "CREATE INDEX IF NOT EXISTS idx_firms_last_checked ON firms(last_checked)",
)


def connect(path: os.PathLike[str] | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection with the pipeline's mandatory PRAGMAs applied.

    Applied on *every* connection: WAL journal mode, busy_timeout=5000ms,
    foreign_keys=ON. Row factory is sqlite3.Row for name-based access.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: os.PathLike[str] | str = DEFAULT_DB_PATH) -> Path:
    """Idempotently create ``pipeline.db`` with all five tables and return its path.

    Creates the parent directory if missing. All DDL is CREATE ... IF NOT EXISTS,
    so a second call is a no-op.
    """
    db_path = Path(path)
    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        conn.execute(_firms_ddl())
        for ddl in _SKELETON_DDL:
            conn.execute(ddl)
        for ddl in _INDEX_DDL:
            conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()
    return db_path.resolve()


def upsert_firm(conn: sqlite3.Connection, record: FirmRecord) -> None:
    """Insert-or-replace a firm row from a FirmRecord, keyed by website.

    Commits the transaction (crash-safe per-row write).
    """
    columns = list(FIRM_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in columns)
    col_list = ", ".join(columns)

    data = record.model_dump()
    # Store enum as its string value and bool as 0/1 for SQLite.
    data["status"] = record.status.value
    data["needs_review"] = 1 if record.needs_review else 0

    conn.execute(
        f"INSERT OR REPLACE INTO firms ({col_list}) VALUES ({placeholders})",
        data,
    )
    conn.commit()


def advance_status(
    conn: sqlite3.Connection, website: str, new_status: str | FirmStatus
) -> None:
    """Move a firm to ``new_status`` iff the transition is allowed, else ValueError.

    Reads the firm's current status by website, validates against
    ALLOWED_TRANSITIONS, and updates inside a committed transaction.
    """
    target = new_status.value if isinstance(new_status, FirmStatus) else str(new_status)

    row = conn.execute(
        "SELECT status FROM firms WHERE website = ?", (website,)
    ).fetchone()
    if row is None:
        raise ValueError(f"No firm with website {website!r}")

    current = row["status"] if isinstance(row, sqlite3.Row) else row[0]
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError(
            f"Disallowed status transition: {current!r} -> {target!r}"
        )

    conn.execute(
        "UPDATE firms SET status = ? WHERE website = ?", (target, website)
    )
    conn.commit()


def stale_firms(conn: sqlite3.Connection, days: int = 90) -> list[str]:
    """Return websites of firms whose last_checked is null or older than ``days``.

    Uses SQLite julianday arithmetic: a firm is stale when it has never been checked
    (last_checked IS NULL) or ``julianday('now') - julianday(last_checked) > days``.
    Firms checked within the window are excluded.
    """
    rows = conn.execute(
        """
        SELECT website FROM firms
        WHERE last_checked IS NULL
           OR (julianday('now') - julianday(last_checked)) > ?
        """,
        (days,),
    ).fetchall()
    return [(r["website"] if isinstance(r, sqlite3.Row) else r[0]) for r in rows]


__all__ = [
    "DEFAULT_DB_PATH",
    "ALLOWED_TRANSITIONS",
    "connect",
    "init_db",
    "upsert_firm",
    "advance_status",
    "stale_firms",
]
