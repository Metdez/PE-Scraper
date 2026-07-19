"""Tests for pescraper.provenance — quote-to-page matching for source_page_url.

Pure-function contract (stdlib difflib only, no I/O, no LLM): see
.planning/phases/02-core-pipeline-single-firm/02-01-PLAN.md Task 3 and
02-RESEARCH.md "Pattern 6: Per-Field Provenance via Code-Side Quote Matching".
"""

from __future__ import annotations


def test_find_source_page_none_quote_returns_none() -> None:
    from pescraper.provenance import find_source_page

    assert find_source_page(None, {"https://a.example": "some content"}) is None


def test_find_source_page_empty_quote_returns_none() -> None:
    from pescraper.provenance import find_source_page

    assert find_source_page("", {"https://a.example": "some content"}) is None


def test_find_source_page_exact_substring_case_insensitive() -> None:
    from pescraper.provenance import find_source_page

    pages = {"https://a.example": "Our fund targets EBITDA of $5M to $25M in the mid-market."}
    assert find_source_page("ebitda of $5m to $25m", pages) == "https://a.example"


def test_find_source_page_no_match_below_threshold_returns_none() -> None:
    from pescraper.provenance import find_source_page

    pages = {"https://a.example": "some other content entirely, nothing related at all"}
    assert (
        find_source_page("totally unrelated text not on any page", pages) is None
    )


def test_find_source_page_multi_page_picks_best_fuzzy_match() -> None:
    from pescraper.provenance import find_source_page

    quote = "We invest in North American lower-middle-market industrial companies."
    pages = {
        "https://a.example": "Random unrelated boilerplate about cookies and privacy policy.",
        "https://b.example": "We invest in North American lower middle market industrial companies with strong management teams.",
    }

    assert find_source_page(quote, pages) == "https://b.example"


def test_find_source_page_empty_pages_dict_returns_none() -> None:
    from pescraper.provenance import find_source_page

    assert find_source_page("some quote", {}) is None
