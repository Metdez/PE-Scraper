"""Field-group Pydantic extraction contracts for qwen3:4b structured output — PIPE-03.

These are the two schemas fed directly to Ollama's ``format=`` parameter (via
``model_json_schema()``), NOT the storage-shaped :class:`pescraper.models.FirmRecord`.
Splitting extraction into a *financial* group and a *categorical* group keeps each
individual JSON schema small, which PITFALLS.md Pitfall 1 and RESEARCH.md's Standard
Stack note both identify as measurably improving a 4B model's structured-output
compliance versus one 24-field mega-schema.

Every numeric/categorical value field carries a sibling ``*_quote: Optional[str]``
field. The model must return a verbatim quote from the source page alongside any
populated value — this quote serves two downstream purposes neither of which this
module implements: (1) :mod:`pescraper.extract`'s numeric sanity clamp reasons about
scale from the value alone, and (2) a later code-side quote-to-page matcher
(RESEARCH.md Pattern 6, not this plan) determines ``source_page_url`` by string-
matching the quote against fetched page text — the model is never trusted to report
a URL directly (small models are unreliable at echoing back exact strings verbatim).

``deal_types`` is a ``Literal[...]`` of the seven CONTEXT.md-locked values. Pydantic
v2 renders a ``Literal`` of strings as a JSON-schema ``enum`` in
``model_json_schema()``, which Ollama's constrained decoding then enforces at the
token level — the controlled vocabulary is a schema-level guarantee, not a prompt
instruction that a model could ignore.

Prompt files (static system-prompt text, versioned by filename suffix) live under
``src/pescraper/prompts/`` and are loaded by both this module's docstring convention
and :mod:`pescraper.extract`'s runtime loading via::

    from pathlib import Path
    PROMPT_DIR = Path(__file__).parent / "prompts"
    text = (PROMPT_DIR / "financial_v1.txt").read_text(encoding="utf-8")

Both this module and ``extract.py`` MUST resolve prompt paths via
``Path(__file__).parent / "prompts" / "<name>"`` so the loading contract never drifts
between the two modules.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# The seven CONTEXT.md-locked deal-type values, enforced as a hard JSON-schema enum.
DealType = Literal[
    "Buyout",
    "Recap",
    "Minority",
    "Growth Equity",
    "Venture",
    "Mezzanine Debt",
    "Other",
]


class FinancialCriteria(BaseModel):
    """Numeric investment-criteria fields, each paired with a verbatim supporting quote.

    Every ``*_musd`` field is documented (both here and in ``prompts/financial_v1.txt``)
    as already being in millions USD — CONTEXT.md's unit-scale defense-in-depth first
    layer. :mod:`pescraper.extract`'s ``apply_sanity_clamp`` is the second, code-side
    layer that catches the model expressing a value in raw dollars despite the
    instruction.
    """

    firm_name: str = Field(description="Firm name, as stated on the source page(s).")

    rev_min_musd: Optional[float] = Field(
        default=None, description="Revenue minimum, already in millions USD (e.g. $5M -> 5.0)."
    )
    rev_min_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting rev_min_musd."
    )
    rev_max_musd: Optional[float] = Field(
        default=None, description="Revenue maximum, already in millions USD (e.g. $5M -> 5.0)."
    )
    rev_max_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting rev_max_musd."
    )

    ebitda_min_musd: Optional[float] = Field(
        default=None, description="EBITDA minimum, already in millions USD (e.g. $5M -> 5.0)."
    )
    ebitda_min_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting ebitda_min_musd."
    )
    ebitda_max_musd: Optional[float] = Field(
        default=None, description="EBITDA maximum, already in millions USD (e.g. $5M -> 5.0)."
    )
    ebitda_max_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting ebitda_max_musd."
    )

    ev_min_musd: Optional[float] = Field(
        default=None,
        description="Enterprise value minimum, already in millions USD (e.g. $5M -> 5.0).",
    )
    ev_min_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting ev_min_musd."
    )
    ev_max_musd: Optional[float] = Field(
        default=None,
        description="Enterprise value maximum, already in millions USD (e.g. $5M -> 5.0).",
    )
    ev_max_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting ev_max_musd."
    )

    check_min_musd: Optional[float] = Field(
        default=None, description="Check size minimum, already in millions USD (e.g. $5M -> 5.0)."
    )
    check_min_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting check_min_musd."
    )
    check_max_musd: Optional[float] = Field(
        default=None, description="Check size maximum, already in millions USD (e.g. $5M -> 5.0)."
    )
    check_max_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting check_max_musd."
    )

    aum_musd: Optional[float] = Field(
        default=None,
        description="Assets under management, already in millions USD (e.g. $5M -> 5.0).",
    )
    aum_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting aum_musd."
    )


class CategoricalCriteria(BaseModel):
    """Categorical / metadata investment-criteria fields.

    ``deal_types`` is constrained to the seven CONTEXT.md-locked values via a
    ``Literal`` (rendered as a JSON-schema ``enum`` by Pydantic v2) — Ollama's
    constrained decoding cannot emit anything outside this vocabulary.
    """

    firm_name: str = Field(description="Firm name, as stated on the source page(s).")

    type: Optional[str] = Field(
        default=None, description="Firm type (e.g. Private Equity, Growth Equity, Family Office)."
    )
    state: Optional[str] = Field(default=None, description="US state where the firm is headquartered.")
    city: Optional[str] = Field(default=None, description="City where the firm is headquartered.")

    deal_types: Optional[DealType] = Field(
        default=None,
        description=(
            "Deal type, restricted to exactly one of: Buyout, Recap, Minority, "
            "Growth Equity, Venture, Mezzanine Debt, Other. Return null if none stated."
        ),
    )
    deal_types_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting deal_types."
    )

    sector_tier1: Optional[str] = Field(
        default=None, description="Primary sector/industry focus, as stated on the source page(s)."
    )
    sector_tier1_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the source page supporting sector_tier1."
    )

    activity: Optional[str] = Field(
        default=None, description="Recent investment activity summary, as stated on the source page(s)."
    )
    last_deal: Optional[str] = Field(
        default=None, description="Most recently mentioned deal, as stated on the source page(s)."
    )
    fund_name: Optional[str] = Field(
        default=None, description="Current fund name, as stated on the source page(s)."
    )
    us_investments: Optional[int] = Field(
        default=None, description="Count of US investments, if a specific number is stated."
    )


__all__ = ["DealType", "FinancialCriteria", "CategoricalCriteria"]
