"""Company schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CompanyOut(BaseModel):
    id: int
    cik: str
    ticker: str
    name: str
    sector: str | None = None
    industry: str | None = None
    sic_code: str | None = None
    exchange: str | None = None
    fiscal_year_end: str | None = None
    market_cap: int | None = None
    employee_count: int | None = None
    headquarters: str | None = None
    description: str | None = None
    website: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompanyBrief(BaseModel):
    """Lightweight company listing item."""
    ticker: str
    name: str
    sector: str | None = None

    model_config = {"from_attributes": True}
