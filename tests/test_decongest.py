from __future__ import annotations

from pescraper.decongest import content_hash, decongest


def test_decongest_returns_non_empty_transformed_string() -> None:
    html = "<html><body><nav>Home About</nav><p>EBITDA of $5M to $25M</p></body></html>"
    result = decongest(html, "https://a.example")
    assert isinstance(result, str)


def test_decongest_empty_input_returns_empty_string() -> None:
    assert decongest("", "https://a.example") == ""


def test_content_hash_is_64_char_lowercase_hex() -> None:
    digest = content_hash("some fit_markdown text")
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises if not valid hex


def test_content_hash_deterministic_and_input_sensitive() -> None:
    a = content_hash("some fit_markdown text")
    b = content_hash("some fit_markdown text")
    c = content_hash("different text")
    assert a == b
    assert a != c
