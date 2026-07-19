"""Pydantic v2 model of the fixed 24-column firm record — the extraction contract.

This module is the *single source of truth* for the firm schema. ``db.py`` builds
its ``firms`` DDL from :data:`FIRM_COLUMNS` and Phase 2's extractor feeds
``FirmRecord.model_json_schema()`` straight into Ollama's ``format`` parameter, so
the constrained-output shape and the SQLite shape can never drift apart.

Every criteria field is **nullable by default** (only ``firm_name`` is required).
This is deliberate per PITFALLS Pitfall 1: a 4B model under schema pressure to fill
14 numeric fields fabricates plausible mid-market ranges. ``null`` must be the cheap,
correct answer when a page states nothing — never a penalized one.

Snake_case field -> display label (the 24 columns, in schema order):

    firm_name        -> Firm Name
    type             -> Type
    state            -> State
    city             -> City
    website          -> Website
    us_investments   -> US Investments
    rev_min_musd     -> Rev Min ($M)
    rev_max_musd     -> Rev Max ($M)
    ebitda_min_musd  -> EBITDA Min ($M)
    ebitda_max_musd  -> EBITDA Max ($M)
    ev_min_musd      -> EV Min ($M)
    ev_max_musd      -> EV Max ($M)
    check_min_musd   -> Check Min ($M)
    check_max_musd   -> Check Max ($M)
    deal_types       -> Deal Types
    sector_tier1     -> Sector Tier 1
    aum_musd         -> AUM ($M)
    activity         -> Activity
    last_deal        -> Last Deal
    fund_name        -> Fund Name
    confidence       -> Confidence
    needs_review     -> Needs Review
    last_checked     -> Last Checked
    status           -> Status
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FirmStatus(str, Enum):
    """Firm lifecycle: pending -> in_progress -> complete | needs_review.

    A ``str`` Enum so the value serializes as the bare status string in JSON and
    stores as TEXT in SQLite without adapters.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    NEEDS_REVIEW = "needs_review"


class FirmRecord(BaseModel):
    """One firm's investment-criteria row — the 24-column schema.

    Field order matches :data:`FIRM_COLUMNS` and PROJECT.md's display-label order.
    All fields except ``firm_name`` are nullable and default to ``None`` (or the
    documented non-null default for ``needs_review`` / ``status``).
    """

    firm_name: str = Field(description="Firm Name")
    type: Optional[str] = Field(default=None, description="Type")
    state: Optional[str] = Field(default=None, description="State")
    city: Optional[str] = Field(default=None, description="City")
    website: Optional[str] = Field(default=None, description="Website")
    us_investments: Optional[int] = Field(default=None, description="US Investments")
    rev_min_musd: Optional[float] = Field(default=None, description="Rev Min ($M)")
    rev_max_musd: Optional[float] = Field(default=None, description="Rev Max ($M)")
    ebitda_min_musd: Optional[float] = Field(default=None, description="EBITDA Min ($M)")
    ebitda_max_musd: Optional[float] = Field(default=None, description="EBITDA Max ($M)")
    ev_min_musd: Optional[float] = Field(default=None, description="EV Min ($M)")
    ev_max_musd: Optional[float] = Field(default=None, description="EV Max ($M)")
    check_min_musd: Optional[float] = Field(default=None, description="Check Min ($M)")
    check_max_musd: Optional[float] = Field(default=None, description="Check Max ($M)")
    deal_types: Optional[str] = Field(default=None, description="Deal Types")
    sector_tier1: Optional[str] = Field(default=None, description="Sector Tier 1")
    aum_musd: Optional[float] = Field(default=None, description="AUM ($M)")
    activity: Optional[str] = Field(default=None, description="Activity")
    last_deal: Optional[str] = Field(default=None, description="Last Deal")
    fund_name: Optional[str] = Field(default=None, description="Fund Name")
    confidence: Optional[float] = Field(default=None, description="Confidence")
    needs_review: bool = Field(default=False, description="Needs Review")
    last_checked: Optional[str] = Field(
        default=None, description="Last Checked (ISO-8601 timestamp)"
    )
    status: FirmStatus = Field(default=FirmStatus.PENDING, description="Status")


# The ordered tuple of the 24 field names — db.py and tests share this one source.
FIRM_COLUMNS: tuple[str, ...] = tuple(FirmRecord.model_fields.keys())


__all__ = ["FirmStatus", "FirmRecord", "FIRM_COLUMNS"]
