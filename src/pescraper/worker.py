"""Crash-safe batch worker: claims queued firms, processes them one at a time.

Per-firm commits already happen inside cli.run_firm_pipeline (via db.upsert_firm),
so a kill mid-batch loses at most the one firm in flight — its job stays
'in_progress' and sync_queue_from_firms() re-queues it (and the firm itself,
since Phase 2's status lifecycle allows in_progress -> in_progress) on the next
run. A failing firm is logged with its reason and the batch continues.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pescraper import db
from pescraper.models import FirmStatus

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] | None = None

    def __post_init__(self) -> None:
        if self.failures is None:
            self.failures = []


def sync_queue_from_firms(conn) -> int:
    """(Re-)enqueue every firm that isn't finished and isn't already queued.

    This is the resume mechanism: firms left `pending` (never started) or
    `in_progress` (crashed mid-run) get a fresh job if one isn't already
    outstanding. Idempotent — safe to call at the start of every batch run.
    """
    rows = conn.execute(
        "SELECT website FROM firms WHERE status IN (?, ?)",
        (FirmStatus.PENDING.value, FirmStatus.IN_PROGRESS.value),
    ).fetchall()
    enqueued = 0
    for row in rows:
        website = row["website"]
        if website and not db.job_already_queued(conn, "run_firm", website):
            db.enqueue_job(conn, "run_firm", website, priority=9)
            enqueued += 1
    return enqueued


def sync_queue_from_stale(conn, days: int = 90) -> int:
    """Re-enqueue firms whose last_checked is stale (90-day re-check, AUTO-01)."""
    enqueued = 0
    for website in db.stale_firms(conn, days=days):
        if website and not db.job_already_queued(conn, "run_firm", website):
            db.enqueue_job(conn, "run_firm", website, priority=5)
            enqueued += 1
    return enqueued


@dataclass
class HeartbeatResult:
    skipped: bool
    reason: str
    batch: BatchResult | None = None


async def run_heartbeat(limit: int = 50, db_path=None) -> HeartbeatResult:
    """Unattended entry point (Windows Task Scheduler): the script-gate pattern —
    check for real work first, do nothing (zero-cost) if the queue is empty and
    no firm is stale, and never let an error crash or corrupt the run.
    """
    path = db.init_db(db_path) if db_path else db.init_db()
    conn = db.connect(path)
    try:
        new_from_pending = sync_queue_from_firms(conn)
        new_from_stale = sync_queue_from_stale(conn)
        pending_jobs = db.queue_summary(conn).get("queued", 0)
    finally:
        conn.close()

    if pending_jobs == 0 and new_from_pending == 0 and new_from_stale == 0:
        logger.info("heartbeat: queue empty, no stale firms — nothing to do")
        return HeartbeatResult(skipped=True, reason="queue empty, no stale firms")

    try:
        result = await run_batch(limit=limit, db_path=path)
    except Exception as exc:
        # A heartbeat run must never crash or corrupt the dataset — log and return.
        logger.error("heartbeat batch failed: %s", exc, exc_info=True)
        return HeartbeatResult(skipped=False, reason=f"batch error: {exc}", batch=None)

    return HeartbeatResult(skipped=False, reason="processed queue", batch=result)


async def run_batch(limit: int | None = None, db_path=None) -> BatchResult:
    """Process queued firms one at a time until the queue is empty or limit hit."""
    from pescraper.cli import run_firm_pipeline

    path = db.init_db(db_path) if db_path else db.init_db()
    conn = db.connect(path)
    try:
        sync_queue_from_firms(conn)
    finally:
        conn.close()

    result = BatchResult()
    while limit is None or result.processed < limit:
        conn = db.connect(path)
        try:
            job = db.claim_next_job(conn)
        finally:
            conn.close()

        if job is None:
            break

        website = job["payload"]
        try:
            await run_firm_pipeline(website)
            conn = db.connect(path)
            try:
                db.finish_job(conn, job["id"], "done")
            finally:
                conn.close()
            result.succeeded += 1
        except Exception as exc:  # a failing firm must not kill the batch
            logger.warning("firm failed: %s (%s)", website, exc, exc_info=True)
            conn = db.connect(path)
            try:
                db.finish_job(conn, job["id"], "failed", error=str(exc))
            finally:
                conn.close()
            result.failed += 1
            result.failures.append((website, str(exc)))

        result.processed += 1

    return result


__all__ = [
    "BatchResult",
    "HeartbeatResult",
    "sync_queue_from_firms",
    "sync_queue_from_stale",
    "run_batch",
    "run_heartbeat",
]
