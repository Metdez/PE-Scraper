"""Field-group extraction schemas fed to Ollama's ``format=`` parameter.

Not the bare ``FirmRecord`` (RESEARCH.md Pattern 5): ``FirmRecord`` is the storage
row, with no per-field quote/evidence fields, and a single 24-field mega-schema
hurts a 4B model's structured-output compliance (PITFALLS.md Pitfall 1). Two
smaller schemas — financial and categorical — each pair a value field with a
sibling ``*_quote`` field so the numeric sanity-clamp and per-field provenance
(PIPE-05) both have the evidence string they need.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

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
    """Numeric investment-criteria ranges, already in $M, plus verbatim quotes."""

    firm_name: str
    rev_min_musd: Optional[float] = Field(None, description="Revenue min, already in $M")
    rev_min_quote: Optional[str] = Field(None, description="Verbatim quote supporting rev_min_musd")
    rev_max_musd: Optional[float] = Field(None, description="Revenue max, already in $M")
    rev_max_quote: Optional[str] = None
    ebitda_min_musd: Optional[float] = Field(None, description="EBITDA min, already in $M")
    ebitda_min_quote: Optional[str] = None
    ebitda_max_musd: Optional[float] = Field(None, description="EBITDA max, already in $M")
    ebitda_max_quote: Optional[str] = None
    ev_min_musd: Optional[float] = Field(None, description="Enterprise value min, already in $M")
    ev_min_quote: Optional[str] = None
    ev_max_musd: Optional[float] = Field(None, description="Enterprise value max, already in $M")
    ev_max_quote: Optional[str] = None
    check_min_musd: Optional[float] = Field(None, description="Equity check min, already in $M")
    check_min_quote: Optional[str] = None
    check_max_musd: Optional[float] = Field(None, description="Equity check max, already in $M")
    check_max_quote: Optional[str] = None
    aum_musd: Optional[float] = Field(None, description="Assets under management, already in $M")
    aum_quote: Optional[str] = None


class CategoricalCriteria(BaseModel):
    """Non-numeric investment-criteria fields, plus verbatim quotes."""

    firm_name: str
    type: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    deal_types: Optional[DealType] = None
    deal_types_quote: Optional[str] = None
    sector_tier1: Optional[str] = None
    sector_tier1_quote: Optional[str] = None
    activity: Optional[str] = None
    last_deal: Optional[str] = None
    fund_name: Optional[str] = None
    us_investments: Optional[int] = None


# Every *_musd field name shared between FinancialCriteria and the sanity clamp.
MUSD_FIELDS: tuple[str, ...] = (
    "rev_min_musd",
    "rev_max_musd",
    "ebitda_min_musd",
    "ebitda_max_musd",
    "ev_min_musd",
    "ev_max_musd",
    "check_min_musd",
    "check_max_musd",
    "aum_musd",
)

__all__ = [
    "DealType",
    "FinancialCriteria",
    "CategoricalCriteria",
    "MUSD_FIELDS",
]
