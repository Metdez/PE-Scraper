"""qwen3:4b structured extraction via Ollama — PIPE-03.

The highest-variance module in the whole project: every mitigation here was
informed by a live probe against the actually-installed qwen3:4b (RESEARCH.md),
not assumed from documentation. Four defense-in-depth layers, all non-negotiable:

1. **Field-group schemas** (:mod:`pescraper.extract_schemas`), not the bare
   24-column ``FirmRecord`` — smaller schemas measurably improve a 4B model's
   structured-output compliance.
2. **Explicit ``num_ctx=16384``** on every ``ollama.chat`` call. Ollama's runtime
   context allocation defaults to 4096 regardless of the model's trained context
   length (live-verified, RESEARCH.md Pitfall 2) — a ~20,000-char multi-page
   prompt would silently front-truncate at the default. No code path in this
   module may omit ``num_ctx``.
3. **Hardened ``strip_think``**. ``think=False`` does not always fully suppress
   qwen3's reasoning; RESEARCH.md's live probe observed a leaked think block with
   no matching opening ``<think>`` tag — a bare ``</think>`` terminator only.
   ``doctor.py``'s anchored-at-start regex would not catch that; this module's
   ``strip_think`` handles both cases.
4. **Code-side numeric sanity clamp**. Even with the millions-USD prompt/schema
   instruction, qwen3:4b was observed (this session's live probe) to sometimes
   emit a raw-dollar value instead (e.g. ``$40M`` -> ``40001000``) — any value
   whose magnitude exceeds :data:`SANITY_CLAMP_THRESHOLD` is assumed raw-dollar,
   divided by 1e6, and logged as a warning for the Phase 3 benchmark to audit.

Prompt files are loaded from ``src/pescraper/prompts/`` via the same
``Path(__file__).parent / "prompts" / "<name>"`` convention documented in
:mod:`pescraper.extract_schemas`'s module docstring, so the two modules can never
drift on where prompts live.

Following ``doctor.py``'s established convention (and ``CLAUDE.md``'s
lazy-import-heavy-modules pattern), ``ollama`` is imported lazily inside each
extraction function's body, not at module import time.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from pescraper.extract_schemas import CategoricalCriteria, FinancialCriteria

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

# Multi-page prompt assembly budget (CONTEXT.md's decision): ~6,000 chars/page,
# ~20,000 chars total, lowest-priority (later-ranked) pages dropped first when
# the running total would exceed the total cap.
PER_PAGE_CHAR_CAP = 6000
TOTAL_CHAR_CAP = 20000

# Any *_musd value whose magnitude exceeds this is assumed to be a raw-dollar
# figure the model failed to scale to millions, and is auto-divided by 1e6.
SANITY_CLAMP_THRESHOLD = 100_000

_THINK_ANCHORED = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
# Handles a leaked think block with NO matching opening <think> tag (RESEARCH.md
# Pitfall 3, live-probed against qwen3:4b): strip everything up to and including
# the first </think>.
_THINK_UNANCHORED_CLOSE = re.compile(r"^.*?</think>\s*", re.DOTALL)


def _load_prompt(name: str) -> str:
    """Load a versioned system-prompt file from ``src/pescraper/prompts/``."""
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def assemble_prompt(
    pages: dict[str, str],
    per_page_char_cap: int = PER_PAGE_CHAR_CAP,
    total_char_cap: int = TOTAL_CHAR_CAP,
) -> str:
    """Assemble the multi-page extraction prompt under CONTEXT.md's char budget.

    Iterates ``pages`` in dict order (the caller's relevance-rank order, per
    ``crawl.select_pages``), truncates each page's text to ``per_page_char_cap``,
    and emits a ``"## Source: {url}"`` header per page so provenance stays
    traceable. Once including the next page's block would exceed
    ``total_char_cap``, that page and every page after it (lowest-priority, by
    insertion order) is dropped entirely rather than truncated mid-page.
    """
    blocks: list[str] = []
    total = 0
    for url, text in pages.items():
        truncated = text[:per_page_char_cap]
        block = f"## Source: {url}\n{truncated}\n\n"
        if total + len(block) > total_char_cap:
            break
        blocks.append(block)
        total += len(block)
    return "".join(blocks)


def strip_think(content: str | None) -> str:
    """Defensively strip a leaked ``<think>...</think>`` block, anchored or not.

    Handles two cases, both observed live against qwen3:4b (RESEARCH.md
    Pitfall 3): a properly-anchored block starting with ``<think>``, AND a bare
    ``</think>`` terminator with no matching opening tag (the model's response
    began mid-reasoning). Content with no think markers at all is returned
    unchanged. Never raises.
    """
    content = content or ""
    if "<think>" in content:
        return _THINK_ANCHORED.sub("", content)
    if "</think>" in content:
        return _THINK_UNANCHORED_CLOSE.sub("", content)
    return content


def apply_sanity_clamp(value: float | None) -> float | None:
    """Recover a raw-dollar value the model failed to scale to millions USD.

    If ``value`` is non-null and its magnitude exceeds
    :data:`SANITY_CLAMP_THRESHOLD`, it is assumed to be a raw-dollar figure
    (e.g. ``40001000.0`` instead of ``40.001``), divided by 1e6, and the
    correction is logged as a warning so the Phase 3 benchmark can audit how
    often this defense-in-depth layer fires. Values at or under the threshold,
    and ``None``, pass through unchanged.
    """
    if value is not None and abs(value) > SANITY_CLAMP_THRESHOLD:
        clamped = value / 1e6
        logger.warning(
            "apply_sanity_clamp: raw-dollar value %s exceeds threshold %s — "
            "clamped to %s (assumed millions-USD scale error)",
            value,
            SANITY_CLAMP_THRESHOLD,
            clamped,
        )
        return clamped
    return value


async def extract_financial(
    pages: dict[str, str], model: str = "qwen3:4b"
) -> FinancialCriteria:
    """Extract financial investment-criteria fields via Ollama structured output.

    Every ``*_musd`` field on the parsed result passes through
    :func:`apply_sanity_clamp` before returning. ``num_ctx=16384`` and
    ``think=False`` are set on every call — non-negotiable per RESEARCH.md's
    live-verified Pitfall 2.
    """
    import ollama

    prompt_text = _load_prompt("financial_v1.txt")
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": assemble_prompt(pages)},
    ]
    resp = await asyncio.to_thread(
        ollama.chat,
        model=model,
        messages=messages,
        format=FinancialCriteria.model_json_schema(),
        think=False,
        options={"temperature": 0, "num_ctx": 16384},
    )
    content = strip_think(resp.message.content)
    parsed = FinancialCriteria.model_validate_json(content)

    musd_fields = [name for name in FinancialCriteria.model_fields if name.endswith("_musd")]
    updates = {name: apply_sanity_clamp(getattr(parsed, name)) for name in musd_fields}
    return parsed.model_copy(update=updates)


async def extract_categorical(
    pages: dict[str, str], model: str = "qwen3:4b"
) -> CategoricalCriteria:
    """Extract categorical/metadata investment-criteria fields via Ollama.

    ``num_ctx=16384`` and ``think=False`` are set on every call — non-negotiable
    per RESEARCH.md's live-verified Pitfall 2. ``deal_types`` is constrained to
    the seven CONTEXT.md-locked values by :class:`CategoricalCriteria`'s JSON
    schema ``enum``, not by prompt instruction alone.
    """
    import ollama

    prompt_text = _load_prompt("categorical_v1.txt")
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": assemble_prompt(pages)},
    ]
    resp = await asyncio.to_thread(
        ollama.chat,
        model=model,
        messages=messages,
        format=CategoricalCriteria.model_json_schema(),
        think=False,
        options={"temperature": 0, "num_ctx": 16384},
    )
    content = strip_think(resp.message.content)
    return CategoricalCriteria.model_validate_json(content)


__all__ = [
    "PROMPT_DIR",
    "PER_PAGE_CHAR_CAP",
    "TOTAL_CHAR_CAP",
    "SANITY_CLAMP_THRESHOLD",
    "assemble_prompt",
    "strip_think",
    "apply_sanity_clamp",
    "extract_financial",
    "extract_categorical",
]
