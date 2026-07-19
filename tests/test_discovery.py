from __future__ import annotations

from pescraper import db
from pescraper.models import FirmRecord


def _conn(tmp_path):
    path = tmp_path / "pipeline.db"
    db.init_db(path)
    return db.connect(path)


def test_discover_firms_dedupes_and_queues_only_pe_candidates(tmp_path) -> None:
    from pescraper.discovery import SearchResult, discover_firms
    from pescraper.queue import queue_summary

    conn = _conn(tmp_path)
    db.upsert_firm(conn, FirmRecord(firm_name="Known Capital", website="https://known.example"))
    results = [
        SearchResult("Known Capital", "https://known.example/about", "private equity investments"),
        SearchResult("New Buyout Partners", "https://newpe.example", "private equity buyout firm"),
        SearchResult("Accounting Services", "https://accounting.example", "tax and audit services"),
    ]

    discovered = discover_firms(conn, results)

    assert [firm.firm_name for firm in discovered] == ["New Buyout Partners"]
    assert db.get_firm(conn, "https://newpe.example") is not None
    assert queue_summary(conn)["queued"] == 1


def test_recover_firm_url_updates_missing_website_and_requeues(tmp_path) -> None:
    from pescraper.discovery import SearchResult, recover_firm_url

    conn = _conn(tmp_path)
    db.upsert_firm(conn, FirmRecord(firm_name="Lost Capital", website=None))

    recovered = recover_firm_url(
        conn,
        "Lost Capital",
        [SearchResult("Lost Capital", "https://lost.example/about", "private equity firm")],
    )

    assert recovered == "https://lost.example"
    assert db.get_firm(conn, "https://lost.example") is not None
