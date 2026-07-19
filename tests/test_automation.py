from __future__ import annotations

from pescraper import db
from pescraper.models import FirmRecord, FirmStatus


def _conn(tmp_path):
    path = tmp_path / "pipeline.db"
    db.init_db(path)
    return db.connect(path)


def test_heartbeat_skips_processor_when_no_work(tmp_path) -> None:
    from pescraper.automation import heartbeat

    called = False

    def processor(url: str):
        nonlocal called
        called = True
        raise AssertionError(url)

    result = heartbeat(_conn(tmp_path), processor, log_path=tmp_path / "heartbeat.log")

    assert result.skipped is True
    assert called is False


def test_heartbeat_processes_stale_firm_and_surfaces_error(tmp_path) -> None:
    from pescraper.automation import heartbeat

    conn = _conn(tmp_path)
    db.upsert_firm(
        conn,
        FirmRecord(
            firm_name="Blocked Capital",
            website="https://blocked.example",
            status=FirmStatus.COMPLETE,
            last_checked="2020-01-01T00:00:00+00:00",
        ),
    )
    log_path = tmp_path / "heartbeat.log"

    def processor(url: str):
        raise RuntimeError("site blocked")

    result = heartbeat(conn, processor, log_path=log_path)

    assert result.failed == 1
    assert "site blocked" in log_path.read_text(encoding="utf-8")


def test_search_firms_answers_structured_dataset_question(tmp_path) -> None:
    from pescraper.dataset import search_firms

    conn = _conn(tmp_path)
    db.upsert_firm(
        conn,
        FirmRecord(
            firm_name="Industrial Buyout Partners",
            website="https://ibp.example",
            ebitda_min_musd=5,
            ebitda_max_musd=25,
            deal_types="Buyout",
            sector_tier1="Industrials",
        ),
    )
    db.upsert_firm(
        conn,
        FirmRecord(
            firm_name="Software Growth Fund",
            website="https://sgf.example",
            ebitda_min_musd=20,
            ebitda_max_musd=80,
            deal_types="Growth",
            sector_tier1="Technology",
        ),
    )

    matches = search_firms(
        conn,
        ebitda_min=5,
        ebitda_max=25,
        deal_type="buyout",
        sector="industrial",
    )

    assert [firm.firm_name for firm in matches] == ["Industrial Buyout Partners"]
