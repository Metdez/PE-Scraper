"""Offline contract tests for the extraction module (PIPE-03).

``ollama.chat`` is monkeypatched exactly like ``tests/test_doctor.py``'s established
convention — no real Ollama server is contacted. These tests lock the exact call
shape (``format=``, ``think=False``, ``options={"num_ctx": 16384, ...}``), the
char-budget truncation contract of ``assemble_prompt``, the hardened ``strip_think``
(both the anchored AND unanchored ``</think>`` cases RESEARCH.md's live probe
surfaced), and ``apply_sanity_clamp``'s raw-dollar recovery.
"""

from __future__ import annotations

import asyncio
import logging

from pescraper import extract
from pescraper.extract import (
    SANITY_CLAMP_THRESHOLD,
    apply_sanity_clamp,
    assemble_prompt,
    extract_categorical,
    extract_financial,
    strip_think,
)
from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


def test_assemble_prompt_truncates_per_page_and_keeps_headers() -> None:
    pages = {
        "https://a.example": "x" * 7000,
        "https://b.example": "y" * 7000,
    }
    result = assemble_prompt(pages)

    assert "## Source: https://a.example" in result
    assert "## Source: https://b.example" in result
    assert "x" * 6000 in result
    assert "x" * 6001 not in result
    assert "y" * 6000 in result
    assert "y" * 6001 not in result


def test_assemble_prompt_drops_lowest_priority_pages_over_total_cap() -> None:
    pages = {
        "https://p1.example": "a" * 6000,
        "https://p2.example": "b" * 6000,
        "https://p3.example": "c" * 6000,
        "https://p4.example": "d" * 6000,
    }
    result = assemble_prompt(pages)

    # First-ranked pages kept intact.
    assert "## Source: https://p1.example" in result
    assert "## Source: https://p2.example" in result
    assert "## Source: https://p3.example" in result
    # Lowest-priority (last, dict-insertion-order) page dropped once the running
    # total would exceed the 20,000-char total cap.
    assert "## Source: https://p4.example" not in result


def test_strip_think_anchored_case() -> None:
    content = '<think>reasoning here</think>\n\n{"ok": true}'
    assert strip_think(content) == '{"ok": true}'


def test_strip_think_unanchored_case() -> None:
    # RESEARCH.md's live probe: a bare </think> with no matching opening tag.
    content = 'stray reasoning with no opening tag</think>\n\n{"ok": true}'
    assert strip_think(content) == '{"ok": true}'


def test_strip_think_no_markers_returns_unchanged() -> None:
    content = '{"ok": true}'
    assert strip_think(content) == content


def test_strip_think_none_content_returns_empty_string() -> None:
    assert strip_think(None) == ""


def test_apply_sanity_clamp_unchanged_in_range() -> None:
    assert apply_sanity_clamp(5.0) == 5.0


def test_apply_sanity_clamp_divides_out_of_range_and_logs(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger=extract.__name__):
        result = apply_sanity_clamp(40001000.0)
    assert result == 40.001
    assert any(
        "40001000" in record.message or "clamp" in record.message.lower()
        for record in caplog.records
    )


def test_apply_sanity_clamp_none_passthrough() -> None:
    assert apply_sanity_clamp(None) is None


def test_apply_sanity_clamp_threshold_boundary_unchanged() -> None:
    # Exactly at the threshold: unchanged — only strictly-greater triggers the clamp.
    boundary = float(SANITY_CLAMP_THRESHOLD)
    assert apply_sanity_clamp(boundary) == boundary


def test_extract_financial_calls_ollama_with_required_kwargs(monkeypatch) -> None:
    import ollama

    captured: dict = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return _FakeResponse('{"firm_name": "Acme Capital"}')

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = asyncio.run(extract_financial({"https://a.example": "EBITDA of $5M to $25M"}))

    assert isinstance(result, FinancialCriteria)
    assert result.firm_name == "Acme Capital"
    assert captured["format"] == FinancialCriteria.model_json_schema()
    assert captured["think"] is False
    assert captured["options"] == {"temperature": 0, "num_ctx": 16384}


def test_extract_financial_applies_sanity_clamp_to_musd_fields(monkeypatch) -> None:
    import ollama

    def fake_chat(**kwargs):
        return _FakeResponse(
            '{"firm_name": "Acme Capital", "ebitda_min_musd": 40001000.0}'
        )

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = asyncio.run(extract_financial({"https://a.example": "text"}))

    assert result.ebitda_min_musd == 40.001


def test_extract_categorical_calls_ollama_with_required_kwargs(monkeypatch) -> None:
    import ollama

    captured: dict = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return _FakeResponse('{"firm_name": "Acme Capital", "deal_types": "Buyout"}')

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = asyncio.run(extract_categorical({"https://a.example": "We focus on buyouts."}))

    assert isinstance(result, CategoricalCriteria)
    assert result.deal_types == "Buyout"
    assert captured["format"] == CategoricalCriteria.model_json_schema()
    assert captured["think"] is False
    assert captured["options"] == {"temperature": 0, "num_ctx": 16384}


def test_extract_financial_strips_leaked_think_block(monkeypatch) -> None:
    import ollama

    def fake_chat(**kwargs):
        return _FakeResponse(
            'stray reasoning with no opening tag</think>\n\n{"firm_name": "Acme Capital"}'
        )

    monkeypatch.setattr(ollama, "chat", fake_chat)

    result = asyncio.run(extract_financial({"https://a.example": "text"}))
    assert result.firm_name == "Acme Capital"
