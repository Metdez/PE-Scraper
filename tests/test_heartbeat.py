from __future__ import annotations

import asyncio

from pescraper import cli, db, worker
from pescraper.models import FirmRecord, FirmStatus


def test_heartbeat_skips_when_queue_and_stale_both_empty(tmp_path) -> None:
    db_path = tmp_path / "pipeline.db"
    db.init_db(db_path)  # no firms at all

    result = asyncio.run(worker.run_heartbeat(db_path=db_path))
    assert result.skipped is True
    assert result.batch is None


def test_heartbeat_processes_stale_firm(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "pipeline.db"
    conn = db.connect(db.init_db(db_path))
    db.upsert_firm(
        conn,
        FirmRecord(
            firm_name="Old Firm",
            website="https://old.example",
            status=FirmStatus.COMPLETE,
            last_checked="2020-01-01T00:00:00+00:00",
        ),
    )
    conn.close()

    async def fake_pipeline(url: str):
        return FirmRecord(firm_name="Old Firm", website=url, status=FirmStatus.COMPLETE, confidence=0.9)

    monkeypatch.setattr(cli, "run_firm_pipeline", fake_pipeline)

    result = asyncio.run(worker.run_heartbeat(db_path=db_path))
    assert result.skipped is False
    assert result.batch.processed == 1


def test_heartbeat_never_raises_on_batch_error(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "pipeline.db"
    conn = db.connect(db.init_db(db_path))
    db.upsert_firm(conn, FirmRecord(firm_name="A", website="https://a.example"))
    conn.close()

    async def boom(limit=None, db_path=None):
        raise RuntimeError("simulated total failure")

    monkeypatch.setattr(worker, "run_batch", boom)

    result = asyncio.run(worker.run_heartbeat(db_path=db_path))  # must not raise
    assert result.skipped is False
    assert result.batch is None
    assert "error" in result.reason
