"""Offline tests for the batch worker: crash-safe resume, priority ordering,
failure-continues-the-batch. Mocks cli.run_firm_pipeline; real tmp_path db."""

from __future__ import annotations

import asyncio

from pescraper import cli, db, worker
from pescraper.models import FirmRecord, FirmStatus


def _init(tmp_path):
    return db.connect(db.init_db(tmp_path / "pipeline.db"))


def test_claim_next_job_respects_priority(tmp_path) -> None:
    conn = _init(tmp_path)
    db.enqueue_job(conn, "run_firm", "https://low.example", priority=9)
    db.enqueue_job(conn, "run_firm", "https://urgent.example", priority=0)

    job = db.claim_next_job(conn)
    assert job["payload"] == "https://urgent.example"
    conn.close()


def test_claim_next_job_empty_queue_returns_none(tmp_path) -> None:
    conn = _init(tmp_path)
    assert db.claim_next_job(conn) is None
    conn.close()


def test_sync_queue_from_firms_requeues_pending_and_in_progress(tmp_path) -> None:
    conn = _init(tmp_path)
    db.upsert_firm(conn, FirmRecord(firm_name="A", website="https://a.example"))
    db.upsert_firm(
        conn,
        FirmRecord(firm_name="B", website="https://b.example", status=FirmStatus.IN_PROGRESS),
    )
    db.upsert_firm(
        conn,
        FirmRecord(firm_name="C", website="https://c.example", status=FirmStatus.COMPLETE),
    )

    enqueued = worker.sync_queue_from_firms(conn)
    assert enqueued == 2  # A (pending) and B (crashed in_progress); C is done

    payloads = {r["payload"] for r in conn.execute("SELECT payload FROM jobs").fetchall()}
    assert payloads == {"https://a.example", "https://b.example"}
    conn.close()


def test_sync_queue_is_idempotent(tmp_path) -> None:
    conn = _init(tmp_path)
    db.upsert_firm(conn, FirmRecord(firm_name="A", website="https://a.example"))
    worker.sync_queue_from_firms(conn)
    second_pass = worker.sync_queue_from_firms(conn)
    assert second_pass == 0  # already has a live queued job, not duplicated
    conn.close()


def test_run_batch_continues_after_a_failure(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "pipeline.db"
    conn = db.connect(db.init_db(db_path))
    db.upsert_firm(conn, FirmRecord(firm_name="Good", website="https://good.example"))
    db.upsert_firm(conn, FirmRecord(firm_name="Bad", website="https://bad.example"))
    conn.close()

    async def fake_pipeline(url: str):
        if "bad" in url:
            raise RuntimeError("simulated crawl timeout")
        return FirmRecord(firm_name="Good", website=url, status=FirmStatus.COMPLETE, confidence=0.9)

    monkeypatch.setattr(cli, "run_firm_pipeline", fake_pipeline)

    result = asyncio.run(worker.run_batch(db_path=db_path))

    assert result.processed == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.failures[0][0] == "https://bad.example"

    conn = db.connect(db_path)
    jobs = {r["payload"]: r["status"] for r in conn.execute("SELECT payload, status FROM jobs")}
    assert jobs["https://good.example"] == "done"
    assert jobs["https://bad.example"] == "failed"
    conn.close()


def test_run_batch_respects_limit(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "pipeline.db"
    conn = db.connect(db.init_db(db_path))
    for i in range(3):
        db.upsert_firm(conn, FirmRecord(firm_name=f"F{i}", website=f"https://f{i}.example"))
    conn.close()

    async def fake_pipeline(url: str):
        return FirmRecord(firm_name="F", website=url, status=FirmStatus.COMPLETE, confidence=0.9)

    monkeypatch.setattr(cli, "run_firm_pipeline", fake_pipeline)

    result = asyncio.run(worker.run_batch(limit=2, db_path=db_path))
    assert result.processed == 2
