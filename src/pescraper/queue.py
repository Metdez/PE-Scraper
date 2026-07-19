"""SQLite-backed priority queue with atomic claims and resumable jobs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(slots=True)
class Job:
    id: int
    website: str
    priority: int
    attempts: int


def _ensure_schema(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "error" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN error TEXT")
        conn.commit()


def enqueue(conn: sqlite3.Connection, website: str, priority: int = 9) -> int:
    _ensure_schema(conn)
    existing = conn.execute(
        "SELECT id FROM jobs WHERE kind='firm' AND payload=? AND status IN ('queued','in_progress')",
        (json.dumps({"website": website}),),
    ).fetchone()
    if existing:
        return int(existing["id"])
    cursor = conn.execute(
        "INSERT INTO jobs(kind, payload, priority, status) VALUES('firm', ?, ?, 'queued')",
        (json.dumps({"website": website}), priority),
    )
    conn.commit()
    return int(cursor.lastrowid)


def claim_next_job(conn: sqlite3.Connection) -> Job | None:
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT id, payload, priority, attempts FROM jobs "
            "WHERE status='queued' ORDER BY priority ASC, id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE jobs SET status='in_progress', attempts=attempts+1, claimed_at=?, updated_at=? "
            "WHERE id=? AND status='queued'",
            (now, now, row["id"]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    payload = json.loads(row["payload"])
    return Job(int(row["id"]), payload["website"], int(row["priority"]), int(row["attempts"]) + 1)


def finish_job(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(
        "UPDATE jobs SET status='complete', updated_at=?, error=NULL WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), job_id),
    )
    conn.commit()


def fail_job(conn: sqlite3.Connection, job_id: int, error: str) -> None:
    _ensure_schema(conn)
    conn.execute(
        "UPDATE jobs SET status='failed', updated_at=?, error=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), error[:2000], job_id),
    )
    conn.commit()


def requeue_stale_claims(conn: sqlite3.Connection, minutes: int = 30) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    cursor = conn.execute(
        "UPDATE jobs SET status='queued', claimed_at=NULL WHERE status='in_progress' AND claimed_at < ?",
        (cutoff,),
    )
    conn.commit()
    return int(cursor.rowcount)


def queue_summary(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
    return {str(row["status"]): int(row["count"]) for row in rows}


__all__ = [
    "Job",
    "claim_next_job",
    "enqueue",
    "fail_job",
    "finish_job",
    "queue_summary",
    "requeue_stale_claims",
]
