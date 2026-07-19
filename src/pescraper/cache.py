"""Content-addressed extraction cache with explicit invalidation inputs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria


_POISON_MARKERS = (
    "access denied",
    "enable javascript",
    "captcha",
    "cloudflare ray id",
)


def content_hash(pages: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for url, text in sorted(pages.items()):
        digest.update(url.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _key(kind: str, digest: str, prompt_version: str, model: str) -> str:
    raw = "\0".join((kind, model, prompt_version, digest))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(
    conn: sqlite3.Connection,
    kind: str,
    digest: str,
    prompt_version: str,
    model: str,
) -> dict | None:
    row = conn.execute(
        "SELECT value FROM cache WHERE cache_key=?",
        (_key(kind, digest, prompt_version, model),),
    ).fetchone()
    return json.loads(row["value"]) if row else None


def put_cached(
    conn: sqlite3.Connection,
    kind: str,
    digest: str,
    prompt_version: str,
    model: str,
    value: dict,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO cache(cache_key, kind, content_hash, prompt_version, model, value, created_at) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        (
            _key(kind, digest, prompt_version, model),
            kind,
            digest,
            prompt_version,
            model,
            json.dumps(value, sort_keys=True),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def is_cacheable(pages: dict[str, str]) -> bool:
    combined = "\n".join(pages.values()).casefold()
    return bool(combined.strip()) and not any(marker in combined for marker in _POISON_MARKERS)


def get_cached_pages(
    conn: sqlite3.Connection,
    firm_website: str,
    *,
    max_age_days: int = 90,
) -> dict[str, str] | None:
    rows = conn.execute(
        "SELECT url, fit_markdown FROM pages WHERE firm_website=? "
        "AND (julianday('now') - julianday(fetched_at)) <= ? ORDER BY id",
        (firm_website, max_age_days),
    ).fetchall()
    return {row["url"]: row["fit_markdown"] for row in rows} if rows else None


def put_cached_pages(
    conn: sqlite3.Connection,
    firm_website: str,
    pages: dict[str, str],
) -> bool:
    if not is_cacheable(pages):
        return False
    fetched_at = datetime.now(timezone.utc).isoformat()
    conn.execute("DELETE FROM pages WHERE firm_website=?", (firm_website,))
    for url, markdown in pages.items():
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO pages(firm_website, url, fetched_at, content_hash, fit_markdown) "
            "VALUES(?, ?, ?, ?, ?)",
            (firm_website, url, fetched_at, digest, markdown),
        )
    conn.commit()
    return True


async def extract_cached(
    conn: sqlite3.Connection,
    pages: dict[str, str],
    *,
    model: str = "qwen3:4b",
    financial_version: str = "financial_v1",
    categorical_version: str = "categorical_v1",
) -> tuple[FinancialCriteria, CategoricalCriteria]:
    from pescraper import extract

    digest = content_hash(pages)
    financial_data = get_cached(conn, "financial", digest, financial_version, model)
    categorical_data = get_cached(conn, "categorical", digest, categorical_version, model)

    financial = (
        FinancialCriteria(**financial_data)
        if financial_data is not None
        else await extract.extract_financial(pages, model=model)
    )
    categorical = (
        CategoricalCriteria(**categorical_data)
        if categorical_data is not None
        else await extract.extract_categorical(pages, model=model)
    )

    if is_cacheable(pages):
        if financial_data is None:
            put_cached(
                conn,
                "financial",
                digest,
                financial_version,
                model,
                financial.model_dump(mode="json"),
            )
        if categorical_data is None:
            put_cached(
                conn,
                "categorical",
                digest,
                categorical_version,
                model,
                categorical.model_dump(mode="json"),
            )
    return financial, categorical


__all__ = [
    "content_hash",
    "extract_cached",
    "get_cached",
    "get_cached_pages",
    "is_cacheable",
    "put_cached",
    "put_cached_pages",
]
