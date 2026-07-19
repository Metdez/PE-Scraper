from __future__ import annotations

from pescraper.provenance import find_source_page


def test_none_quote_returns_none() -> None:
    assert find_source_page(None, {"https://a.example": "some text"}) is None


def test_empty_quote_returns_none() -> None:
    assert find_source_page("", {"https://a.example": "some text"}) is None


def test_exact_substring_fast_path() -> None:
    pages = {"https://a.example": "... EBITDA of $5M to $25M ..."}
    assert find_source_page("EBITDA of $5M to $25M", pages) == "https://a.example"


def test_exact_substring_is_case_insensitive() -> None:
    pages = {"https://a.example": "... ebitda of $5M to $25M ..."}
    assert find_source_page("EBITDA OF $5M TO $25M", pages) == "https://a.example"


def test_unrelated_text_returns_none() -> None:
    pages = {"https://a.example": "xyz 123 zzz qqq vvv jjj kkk www ppp"}
    quote = "we specialize in industrial buyouts across the midwest region"
    assert find_source_page(quote, pages) is None


def test_best_fuzzy_match_wins_over_first_key() -> None:
    quote = "EBITDA of $5 million to $25 million for buyouts"
    pages = {
        "https://a.example": "This page is entirely about our portfolio companies and team.",
        "https://b.example": "Our criteria: EBITDA of $5 million to $25 million for buyouts.",
    }
    assert find_source_page(quote, pages) == "https://b.example"
