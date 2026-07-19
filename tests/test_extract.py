"""Offline contract tests for pescraper.extract — mocks ollama.chat per
test_doctor.py's established pattern. No real network/Ollama is touched.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from pescraper import extract
from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria


def _fake_response(content: str, prompt_eval_count: int = 100):
    return SimpleNamespace(
        message=SimpleNamespace(content=content),
        prompt_eval_count=prompt_eval_count,
    )


# --------------------------------------------------------------------------- #
# strip_think
# --------------------------------------------------------------------------- #


def test_strip_think_anchored() -> None:
    content = "<think>reasoning here</think>\n{\"firm_name\": \"Acme\"}"
    assert extract.strip_think(content) == '{"firm_name": "Acme"}'


def test_strip_think_unanchored_missing_open_tag() -> None:
    content = "Hmm, the user asked me to...</think>\n\n{\"firm_name\": \"Acme\"}"
    assert extract.strip_think(content) == '{"firm_name": "Acme"}'


def test_strip_think_no_think_block_passthrough() -> None:
    content = '{"firm_name": "Acme"}'
    assert extract.strip_think(content) == content


def test_strip_think_none_content_returns_empty_string() -> None:
    assert extract.strip_think(None) == ""


# --------------------------------------------------------------------------- #
# assemble_pages
# --------------------------------------------------------------------------- #


def test_assemble_pages_includes_url_headers() -> None:
    pages = {"https://a.example": "some criteria text"}
    assembled = extract.assemble_pages(pages)
    assert "https://a.example" in assembled
    assert "some criteria text" in assembled


def test_assemble_pages_truncates_per_page_budget() -> None:
    pages = {"https://a.test": "q" * 10_000}
    assembled = extract.assemble_pages(pages, per_page_budget=100, total_budget=20_000)
    assert assembled.count("q") == 100


def test_assemble_pages_drops_lowest_priority_pages_over_total_budget() -> None:
    pages = {
        "https://a.example": "x" * 50,
        "https://b.example": "y" * 50,
        "https://c.example": "z" * 50,
    }
    assembled = extract.assemble_pages(pages, per_page_budget=50, total_budget=120)
    assert "https://a.example" in assembled
    assert "https://c.example" not in assembled


def test_assemble_pages_empty_input() -> None:
    assert extract.assemble_pages({}) == ""


# --------------------------------------------------------------------------- #
# numeric sanity clamp
# --------------------------------------------------------------------------- #


def test_apply_numeric_clamp_divides_raw_dollar_value() -> None:
    financial = FinancialCriteria(firm_name="Acme", ebitda_min_musd=40_001_000)
    clamped = extract.apply_numeric_clamp(financial)
    assert clamped.ebitda_min_musd == 40_001_000 / 1_000_000


def test_apply_numeric_clamp_leaves_correct_scale_untouched() -> None:
    financial = FinancialCriteria(firm_name="Acme", ebitda_min_musd=5.0, ebitda_max_musd=25.0)
    clamped = extract.apply_numeric_clamp(financial)
    assert clamped.ebitda_min_musd == 5.0
    assert clamped.ebitda_max_musd == 25.0


def test_apply_numeric_clamp_leaves_none_untouched() -> None:
    financial = FinancialCriteria(firm_name="Acme")
    clamped = extract.apply_numeric_clamp(financial)
    assert clamped.ebitda_min_musd is None


# --------------------------------------------------------------------------- #
# extract_financial / extract_categorical — schema round-trip via mocked ollama.chat
# --------------------------------------------------------------------------- #


def test_extract_financial_round_trips_and_clamps(monkeypatch) -> None:
    import ollama

    payload = {
        "firm_name": "Acme Capital",
        "rev_min_musd": None,
        "rev_min_quote": None,
        "rev_max_musd": None,
        "rev_max_quote": None,
        "ebitda_min_musd": 5_000_000,  # the raw-dollar bug this clamp defends against
        "ebitda_min_quote": "EBITDA of $5 million to $25 million",
        "ebitda_max_musd": 25.0,
        "ebitda_max_quote": "EBITDA of $5 million to $25 million",
        "ev_min_musd": None,
        "ev_min_quote": None,
        "ev_max_musd": None,
        "ev_max_quote": None,
        "check_min_musd": None,
        "check_min_quote": None,
        "check_max_musd": None,
        "check_max_quote": None,
        "aum_musd": None,
        "aum_quote": None,
    }

    def fake_chat(*, model, messages, format, think=None, options=None):
        return _fake_response(json.dumps(payload))

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = extract.extract_financial({"https://a.example": "EBITDA text"}, "Acme Capital")
    assert isinstance(result, FinancialCriteria)
    assert result.ebitda_min_musd == 5.0  # clamped from 5_000_000
    assert result.ebitda_max_musd == 25.0


def test_extract_financial_strips_leaked_think_block(monkeypatch) -> None:
    import ollama

    minimal = {k: None for k in FinancialCriteria.model_fields if k != "firm_name"}
    minimal["firm_name"] = "Acme Capital"

    def fake_chat(*, model, messages, format, think=None, options=None):
        leaked = "Hmm, let me look at the pages...</think>\n" + json.dumps(minimal)
        return _fake_response(leaked)

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = extract.extract_financial({}, "Acme Capital")
    assert result.firm_name == "Acme Capital"


def test_extract_categorical_enforces_deal_type_enum(monkeypatch) -> None:
    import ollama

    minimal = {k: None for k in CategoricalCriteria.model_fields if k != "firm_name"}
    minimal["firm_name"] = "Acme Capital"
    minimal["deal_types"] = "Buyout"

    def fake_chat(*, model, messages, format, think=None, options=None):
        return _fake_response(json.dumps(minimal))

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = extract.extract_categorical({}, "Acme Capital")
    assert isinstance(result, CategoricalCriteria)
    assert result.deal_types == "Buyout"


def test_extract_runs_both_calls(monkeypatch) -> None:
    import ollama

    financial_payload = {k: None for k in FinancialCriteria.model_fields if k != "firm_name"}
    financial_payload["firm_name"] = "Acme Capital"
    categorical_payload = {k: None for k in CategoricalCriteria.model_fields if k != "firm_name"}
    categorical_payload["firm_name"] = "Acme Capital"

    call_schemas: list[dict] = []

    def fake_chat(*, model, messages, format, think=None, options=None):
        call_schemas.append(format)
        if "rev_min_musd" in format["properties"]:
            return _fake_response(json.dumps(financial_payload))
        return _fake_response(json.dumps(categorical_payload))

    monkeypatch.setattr(ollama, "chat", fake_chat)

    financial, categorical = extract.extract({}, "Acme Capital")
    assert isinstance(financial, FinancialCriteria)
    assert isinstance(categorical, CategoricalCriteria)
    assert len(call_schemas) == 2
