"""Offline tests for pescraper.decongest — real crawl4ai markdown generator against
local HTML fixture strings, no network/browser needed (RESEARCH.md's own live-verified
methodology)."""

from __future__ import annotations

from pescraper.decongest import content_hash, decongest

_HTML = "<html><body><nav>Home About</nav><p>EBITDA of $5M to $25M</p></body></html>"


def test_decongest_returns_nonempty_transformed_string() -> None:
    result = decongest(_HTML, "https://a.example")
    assert isinstance(result, str)
    assert result != ""
    assert result != _HTML


def test_decongest_empty_input_never_raises() -> None:
    assert decongest("", "https://a.example") == ""


def test_content_hash_is_64_char_lowercase_hex() -> None:
    digest = content_hash("some fit_markdown text")
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises ValueError if not valid hex


def test_content_hash_deterministic_and_input_sensitive() -> None:
    a1 = content_hash("some fit_markdown text")
    a2 = content_hash("some fit_markdown text")
    b = content_hash("different text")
    assert a1 == a2
    assert a1 != b
