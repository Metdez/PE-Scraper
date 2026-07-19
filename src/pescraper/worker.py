"""Crash-safe batch worker built on the SQLite priority queue."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from pescraper import db
from pescraper.models import FirmRecord
from pescraper.queue import claim_next_job, fail_job, finish_job, requeue_stale_claims


@dataclass(slots=True)
class BatchResult:
    completed: int = 0
    failed: int = 0


def run_batch(
    conn: sqlite3.Connection,
    processor: Callable[[str], FirmRecord],
    limit: int | None = None,
) -> BatchResult:
    """Process queued firms one at a time, committing each terminal outcome."""
    requeue_stale_claims(conn)
    result = BatchResult()
    processed = 0
    while limit is None or processed < limit:
        job = claim_next_job(conn)
        if job is None:
            break
        processed += 1
        try:
            record = processor(job.website)
            db.upsert_firm(conn, record)
            finish_job(conn, job.id)
            result.completed += 1
        except Exception as exc:
            fail_job(conn, job.id, f"{type(exc).__name__}: {exc}")
            result.failed += 1
    return result


__all__ = ["BatchResult", "run_batch"]
