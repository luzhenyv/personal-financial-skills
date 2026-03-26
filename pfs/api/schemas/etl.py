"""ETL schemas."""

from __future__ import annotations

from pydantic import BaseModel


class IngestRequest(BaseModel):
    ticker: str
    years: int = 5
    quarterly: bool = False


class SyncPricesRequest(BaseModel):
    tickers: list[str] | None = None


class IngestResponse(BaseModel):
    message: str
    etl_run_id: int
    ticker: str
