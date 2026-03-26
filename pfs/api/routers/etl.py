"""ETL router — trigger ingestion and query run history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pfs.api.deps import get_db
from pfs.api.schemas.etl import IngestRequest, SyncPricesRequest
from pfs.services import etl as etl_svc

router = APIRouter(prefix="/api/etl", tags=["etl"])


@router.post("/ingest")
def trigger_ingest(body: IngestRequest, db: Session = Depends(get_db)):
    """Start a full company ingestion in a background thread."""
    return etl_svc.start_ingest(db, body.ticker, body.years, body.quarterly)


@router.post("/sync-prices")
def trigger_sync_prices(body: SyncPricesRequest):
    """Sync daily prices for given tickers (or all companies)."""
    return etl_svc.sync_prices(body.tickers)


@router.get("/runs")
def list_runs(
    ticker: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Query EtlRun history with optional filters."""
    return etl_svc.list_runs(db, ticker=ticker, status=status, limit=limit)


@router.get("/runs/{ticker}")
def get_latest_run(ticker: str, db: Session = Depends(get_db)):
    """Get the latest EtlRun for a ticker."""
    result = etl_svc.get_latest_run(db, ticker)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No ETL runs found for {ticker}")
    return result
