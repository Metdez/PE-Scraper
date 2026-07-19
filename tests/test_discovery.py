"""Offline tests for discovery.py — mocks httpx.get with a real captured
DuckDuckGo Lite response shape (live-verified this session) so the suite is
fast and deterministic; no network in the automated gate."""

from __future__ import annotations

from types import SimpleNamespace

from pescraper import db, discovery
from pescraper.models import FirmRecord

SAMPLE_HTML = """
<html><body><table>
<tr><td>
<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.upliftinvestors.com%2F&amp;rut=abc" class='result-link'>Uplift Investors | Middle-Market Private Equity Firm</a>
</td></tr>
<tr><td class='result-snippet'>Uplift Investors is a private equity firm focused on growth equity.</td></tr>
<tr><td>
<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fcompany%2Fsomething&amp;rut=def" class='result-link'>Some Firm - LinkedIn</a>
</td></tr>
<tr><td class='result-snippet'>LinkedIn profile.</td></tr>
<tr><td>
<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffenwaypartners.com%2F&amp;rut=ghi" class='result-link'>Fenway Partners | Middle-Market Private Equity Firm</a>
</td></tr>
<tr><td class='result-snippet'>Fenway Partners is a private equity investment firm.</td></tr>
</table></body></html>
"""


def _fake_get(*args, **kwargs):
    return SimpleNamespace(status_code=200, text=SAMPLE_HTML, raise_for_status=lambda: None)


def test_search_web_parses_and_decodes_ddg_redirect(monkeypatch) -> None:
    monkeypatch.setattr(discovery.httpx, "get", _fake_get)
    results = discovery.search_web("middle market private equity firm")
    urls = [r["url"] for r in results]
    assert "https://www.upliftinvestors.com/" in urls
    assert "https://fenwaypartners.com/" in urls
    titles = [r["title"] for r in results]
    assert "Uplift Investors | Middle-Market Private Equity Firm" in titles


def test_search_web_returns_empty_on_network_failure(monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(discovery.httpx, "get", boom)
    assert discovery.search_web("anything") == []


def test_classify_pe_firm() -> None:
    assert discovery.classify_pe_firm("Fenway Partners", "a private equity firm") is True
    assert discovery.classify_pe_firm("Joe's Pizza Shop", "best pizza in town") is False


def test_is_directory_site() -> None:
    assert discovery.is_directory_site("https://www.linkedin.com/company/x") is True
    assert discovery.is_directory_site("https://fenwaypartners.com/") is False


def test_dedupe_against_existing_filters_known_and_directory_sites() -> None:
    candidates = [
        {"title": "Fenway Partners", "url": "https://fenwaypartners.com/"},
        {"title": "Already Known Firm", "url": "https://known.example/"},
        {"title": "Some Firm - LinkedIn", "url": "https://www.linkedin.com/company/x"},
    ]
    out = discovery.dedupe_against_existing(
        candidates, existing_names={"already known firm"}, existing_domains=set()
    )
    assert [c["url"] for c in out] == ["https://fenwaypartners.com/"]


def test_run_discovery_queues_new_firms(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(discovery.httpx, "get", _fake_get)
    conn = db.connect(db.init_db(tmp_path / "pipeline.db"))
    queued = discovery.run_discovery(conn, ["middle market private equity firm"])
    assert queued == 2  # Uplift + Fenway survive classify+dedupe; LinkedIn is filtered
    payloads = {r["payload"] for r in conn.execute("SELECT payload FROM jobs").fetchall()}
    assert payloads == {"https://www.upliftinvestors.com/", "https://fenwaypartners.com/"}
    conn.close()


def test_run_discovery_skips_already_known_firm(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(discovery.httpx, "get", _fake_get)
    conn = db.connect(db.init_db(tmp_path / "pipeline.db"))
    db.upsert_firm(conn, FirmRecord(firm_name="Fenway Partners", website="https://fenwaypartners.com/"))
    db.upsert_firm(conn, FirmRecord(firm_name="Uplift Investors | Middle-Market Private Equity Firm", website="https://www.upliftinvestors.com/"))
    queued = discovery.run_discovery(conn, ["middle market private equity firm"])
    assert queued == 0  # both candidates already known — nothing new queued
    conn.close()


def test_recover_dead_urls_finds_and_queues_website(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(discovery.httpx, "get", _fake_get)
    conn = db.connect(db.init_db(tmp_path / "pipeline.db"))
    db.upsert_firm(conn, FirmRecord(firm_name="Fenway Partners", website=None))
    recovered = discovery.recover_dead_urls(conn)
    assert recovered == 1
    row = conn.execute("SELECT website FROM firms WHERE firm_name = 'Fenway Partners'").fetchone()
    assert row["website"] == "https://www.upliftinvestors.com/"  # first non-directory hit
    conn.close()
