"""Portfolio request/response schemas."""

import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PortfolioCreate(BaseModel):
    name: str = "default"
    cash: Decimal = Decimal("100000")
    benchmark: str = "SPY"


class TransactionCreate(BaseModel):
    ticker: str
    action: str = Field(..., pattern=r"^(buy|sell|dividend)$")
    shares: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    date: Optional[datetime.date] = None
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    notes: Optional[str] = None


class SnapshotRequest(BaseModel):
    date: Optional[datetime.date] = None


class PositionUpdate(BaseModel):
    conviction: Optional[str] = Field(None, pattern=r"^(high|medium|low)$")
