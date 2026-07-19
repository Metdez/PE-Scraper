"""Token-free heartbeat gate and unattended queue runner."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pescraper import db
from pescraper.models import FirmRecord
from pescraper.queue import enqueue, queue_summary
from pescraper.worker import run_batch


@dataclass(slots=True)
class HeartbeatResult:
    completed: int = 0
    failed: int = 0
    skipped: bool = False


def heartbeat(
    conn: sqlite3.Connection,
    processor: Callable[[str], FirmRecord],
    *,
    log_path: str | Path = "data/heartbeat.log",
    limit: int | None = None,
) -> HeartbeatResult:
    """Queue stale firms, skip cleanly when idle, and surface all run errors."""
    queued = queue_summary(conn).get("queued", 0)
    if not queued:
        for website in db.stale_firms(conn):
            if website:
                enqueue(conn, website)
        queued = queue_summary(conn).get("queued", 0)
    if not queued:
        return HeartbeatResult(skipped=True)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pescraper.heartbeat")
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    def logged_processor(url: str) -> FirmRecord:
        try:
            return processor(url)
        except Exception:
            logger.exception("firm_failed url=%s", url)
            raise

    try:
        result = run_batch(conn, logged_processor, limit=limit)
        logger.info("heartbeat_complete completed=%d failed=%d", result.completed, result.failed)
        return HeartbeatResult(result.completed, result.failed, False)
    finally:
        handler.close()
        logger.removeHandler(handler)


__all__ = ["HeartbeatResult", "heartbeat"]
