"""SearXNG-backed PE firm discovery, deduplication, and URL recovery."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from pescraper import db
from pescraper.models import FirmRecord, FirmStatus
from pescraper.queue import enqueue


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearxClient:
    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(self, query: str) -> list[SearchResult]:
        response = httpx.get(
            f"{self.base_url}/search",
            params={"q": query, "format": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return [
            SearchResult(item.get("title", ""), item["url"], item.get("content", ""))
            for item in response.json().get("results", [])
            if item.get("url")
        ]

    def healthy(self) -> bool:
        try:
            self.search("private equity")
            return True
        except (httpx.HTTPError, ValueError, KeyError):
            return False


def canonical_website(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.casefold().removeprefix("www.")
    return f"{parsed.scheme or 'https'}://{host}"


def _is_pe(result: SearchResult) -> bool:
    text = f"{result.title} {result.snippet}".casefold()
    return any(term in text for term in ("private equity", "buyout", "growth equity"))


def discover_firms(conn: sqlite3.Connection, results: list[SearchResult]) -> list[FirmRecord]:
    existing_rows = conn.execute("SELECT firm_name, website FROM firms").fetchall()
    names = {str(row["firm_name"]).strip().casefold() for row in existing_rows}
    domains = {
        canonical_website(str(row["website"]))
        for row in existing_rows
        if row["website"]
    }
    discovered: list[FirmRecord] = []
    for result in results:
        if not _is_pe(result):
            continue
        website = canonical_website(result.url)
        name = result.title.strip()
        if not name or name.casefold() in names or website in domains:
            continue
        record = FirmRecord(firm_name=name, website=website, status=FirmStatus.PENDING)
        db.upsert_firm(conn, record)
        enqueue(conn, website)
        discovered.append(record)
        names.add(name.casefold())
        domains.add(website)
    return discovered


def recover_firm_url(
    conn: sqlite3.Connection,
    firm_name: str,
    results: list[SearchResult],
) -> str | None:
    candidate = next((item for item in results if _is_pe(item)), None)
    if candidate is None:
        return None
    website = canonical_website(candidate.url)
    row = conn.execute(
        "SELECT rowid, * FROM firms WHERE LOWER(firm_name)=LOWER(?) ORDER BY rowid LIMIT 1",
        (firm_name,),
    ).fetchone()
    if row is None:
        record = FirmRecord(firm_name=firm_name, website=website)
    else:
        data = dict(row)
        data.pop("rowid", None)
        data["website"] = website
        data["status"] = FirmStatus.PENDING
        data["needs_review"] = bool(data["needs_review"])
        record = FirmRecord(**data)
        conn.execute("DELETE FROM firms WHERE rowid=?", (row["rowid"],))
        conn.commit()
    db.upsert_firm(conn, record)
    enqueue(conn, website, priority=0)
    return website


__all__ = [
    "SearchResult",
    "SearxClient",
    "canonical_website",
    "discover_firms",
    "recover_firm_url",
]
