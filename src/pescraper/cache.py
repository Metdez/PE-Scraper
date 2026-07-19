"""Extraction-result memoization cache (CACH-02) over the ``cache`` table.

Key is ``(kind, model, prompt_version, content_hash)`` — identical inputs are
never re-spent. Bumping ``prompt_version`` naturally invalidates stale entries
(new key, cache miss); ``invalidate_stale_prompt_versions`` reclaims them.
Blocked/near-empty content is never cached (defense against caching a JS-shell
page that slipped through with only boilerplate text).
"""

from __future__ import annotations

from datetime import datetime, timezone

MIN_CACHEABLE_LENGTH = 50


def cache_key(*, kind: str, model: str, prompt_version: str, content_hash: str) -> str:
    return f"{kind}:{model}:{prompt_version}:{content_hash}"


def get_cached(conn, *, kind: str, model: str, prompt_version: str, content_hash: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM cache WHERE cache_key = ?",
        (cache_key(kind=kind, model=model, prompt_version=prompt_version, content_hash=content_hash),),
    ).fetchone()
    return row["value"] if row else None


def put_cached(
    conn,
    *,
    kind: str,
    model: str,
    prompt_version: str,
    content_hash: str,
    value: str,
    source_text: str = "",
) -> None:
    """Store a cache entry. No-ops on near-empty source content."""
    if len(source_text) < MIN_CACHEABLE_LENGTH:
        return
    key = cache_key(kind=kind, model=model, prompt_version=prompt_version, content_hash=content_hash)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO cache (cache_key, kind, content_hash, prompt_version, model, value, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, kind, content_hash, prompt_version, model, value, now),
    )
    conn.commit()


def invalidate_stale_prompt_versions(conn, current_prompt_version: str) -> int:
    """Delete cache rows from any prompt_version other than the current one."""
    cur = conn.execute(
        "DELETE FROM cache WHERE prompt_version != ?", (current_prompt_version,)
    )
    conn.commit()
    return cur.rowcount


__all__ = ["MIN_CACHEABLE_LENGTH", "cache_key", "get_cached", "put_cached", "invalidate_stale_prompt_versions"]
