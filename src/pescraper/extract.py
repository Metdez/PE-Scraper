"""qwen3:4b structured extraction — the core PIPE-03 extraction call.

Two Ollama calls per firm (financial + categorical, RESEARCH.md Pattern 5), both
fed the same assembled multi-page prompt. Every call sets ``num_ctx=16384``
explicitly (Pitfall 2 — Ollama's default context window silently truncates a
multi-page prompt) and ``think=False`` with a hardened, unconditional think-strip
(Pitfall 3 — the leaked-reasoning block sometimes lacks an opening ``<think>``
tag). A numeric sanity clamp defends against the unit-scale bug this project's
live probe found (``$40M`` -> ``40001000``): any ``*_musd`` value whose magnitude
exceeds 100,000 is assumed to be raw dollars and divided by 1e6, logged as a
warning for the Phase 3 benchmark to audit.
"""

from __future__ import annotations

import logging
import re

from pescraper.extract_schemas import MUSD_FIELDS, CategoricalCriteria, FinancialCriteria

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3:4b"
PROMPT_VERSION = "v1"

NUM_CTX = 16384
PAGE_CHAR_BUDGET = 6_000
TOTAL_CHAR_BUDGET = 20_000
SANITY_CLAMP_THRESHOLD = 100_000

SYSTEM_PROMPT = (
    "You are a financial data extraction assistant for private equity firm "
    "websites. Extract every fact that IS explicitly stated on the provided "
    "pages, in full — converting units and parsing plain fields (city, state, "
    "fund name) is REQUIRED extraction work, not forbidden inference. Only "
    "leave a field null when the page truly never mentions it; never fabricate "
    "a value the page does not support. Examples: \"Headquartered in Greenwich, "
    "CT\" -> city=\"Greenwich\", state=\"CT\". \"$5.9 billion in assets under "
    "management\" -> aum_musd=5900.0 (convert to millions: multiply billions by "
    "1000). \"$5 million\" -> 5.0. \"$500,000\" -> 0.5. If you find the right "
    "sentence but are unsure how to convert it, still fill in your best-effort "
    "numeric conversion rather than leaving it null. For every populated value "
    "field, populate its sibling *_quote field with the exact verbatim sentence "
    "from the source page that supports it."
)

_THINK_ANCHORED = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
_THINK_UNANCHORED_CLOSE = re.compile(r"^.*?</think>\s*", re.DOTALL)


def strip_think(content: str) -> str:
    """Strip a leaked ``<think>...</think>`` block, anchored or not.

    qwen3's thinking is not perfectly gated by ``think=False`` on every call
    shape; a leaked block has sometimes been observed with no opening
    ``<think>`` tag (RESEARCH.md Pitfall 3). Handles both cases; passes
    through content with neither tag unchanged.
    """
    content = content or ""
    if "<think>" in content:
        return _THINK_ANCHORED.sub("", content)
    if "</think>" in content:
        return _THINK_UNANCHORED_CLOSE.sub("", content)
    return content


def assemble_pages(
    pages: dict[str, str],
    per_page_budget: int = PAGE_CHAR_BUDGET,
    total_budget: int = TOTAL_CHAR_BUDGET,
) -> str:
    """Concatenate pages under a char budget, URL headers preserved for provenance.

    Pages are consumed in dict-iteration order (the caller's priority order —
    crawl.select_pages yields relevance-ranked results first, fallback paths
    after). Each page is truncated to ``per_page_budget`` chars; once adding a
    page would exceed ``total_budget``, remaining (lowest-priority) pages are
    dropped entirely rather than partially included.
    """
    sections: list[str] = []
    total = 0
    for url, text in pages.items():
        truncated = (text or "")[:per_page_budget]
        section = f"### PAGE: {url}\n{truncated}\n"
        if sections and total + len(section) > total_budget:
            break
        sections.append(section)
        total += len(section)
    return "\n".join(sections)


def _clamp_musd(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    if abs(value) > SANITY_CLAMP_THRESHOLD:
        clamped = value / 1_000_000
        logger.warning(
            "sanity clamp: %s=%r exceeded %s, assumed raw-dollar and divided by 1e6 -> %r",
            field,
            value,
            SANITY_CLAMP_THRESHOLD,
            clamped,
        )
        return clamped
    return value


def apply_numeric_clamp(financial: FinancialCriteria) -> FinancialCriteria:
    """Defense-in-depth against unit-scale hallucination (RESEARCH.md Pitfall 5)."""
    data = financial.model_dump()
    for field in MUSD_FIELDS:
        data[field] = _clamp_musd(data[field], field)
    return FinancialCriteria(**data)


def _chat(model: str, user_content: str, schema: dict, num_ctx: int = NUM_CTX) -> tuple[str, object]:
    import ollama

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    options = {"temperature": 0, "num_ctx": num_ctx}

    try:
        resp = ollama.chat(model=model, messages=messages, format=schema, think=False, options=options)
    except TypeError:
        resp = ollama.chat(model=model, messages=messages, format=schema, options=options)

    prompt_eval_count = getattr(resp, "prompt_eval_count", None)
    if prompt_eval_count is not None and prompt_eval_count > 0.8 * num_ctx:
        logger.warning(
            "prompt_eval_count=%s is within 80%% of num_ctx=%s — possible truncation",
            prompt_eval_count,
            num_ctx,
        )

    content = strip_think(resp.message.content)
    return content, resp


def extract_financial(
    pages: dict[str, str],
    firm_name: str,
    model: str = DEFAULT_MODEL,
) -> FinancialCriteria:
    """Extract numeric criteria, sanity-clamped, from the assembled pages."""
    user_content = f"Firm name: {firm_name}\n\n{assemble_pages(pages)}"
    content, _ = _chat(model, user_content, FinancialCriteria.model_json_schema())
    parsed = FinancialCriteria.model_validate_json(content)
    return apply_numeric_clamp(parsed)


def extract_categorical(
    pages: dict[str, str],
    firm_name: str,
    model: str = DEFAULT_MODEL,
) -> CategoricalCriteria:
    """Extract categorical criteria from the assembled pages."""
    user_content = f"Firm name: {firm_name}\n\n{assemble_pages(pages)}"
    content, _ = _chat(model, user_content, CategoricalCriteria.model_json_schema())
    return CategoricalCriteria.model_validate_json(content)


def extract(
    pages: dict[str, str],
    firm_name: str,
    model: str = DEFAULT_MODEL,
) -> tuple[FinancialCriteria, CategoricalCriteria]:
    """Run both extraction calls for one firm; returns (financial, categorical)."""
    financial = extract_financial(pages, firm_name, model)
    categorical = extract_categorical(pages, firm_name, model)
    return financial, categorical


__all__ = [
    "DEFAULT_MODEL",
    "PROMPT_VERSION",
    "NUM_CTX",
    "PAGE_CHAR_BUDGET",
    "TOTAL_CHAR_BUDGET",
    "SANITY_CLAMP_THRESHOLD",
    "SYSTEM_PROMPT",
    "strip_think",
    "assemble_pages",
    "apply_numeric_clamp",
    "extract_financial",
    "extract_categorical",
    "extract",
]
