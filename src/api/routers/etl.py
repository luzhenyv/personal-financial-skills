"""ETL router — trigger ingestion and query run history."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.models import EtlRun

router = APIRouter(prefix="/api/etl", tags=["etl"])


# ── Request schemas ──────────────────────────


class IngestRequest(BaseModel):
    ticker: str
    years: int = 5
    quarterly: bool = False


class SyncPricesRequest(BaseModel):
    tickers: list[str] | None = None


# ── Helpers ──────────────────────────────────


def _row_to_dict(obj) -> dict[str, Any]:
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        result[col.name] = val
    return result


def _run_ingest(ticker: str, years: int, quarterly: bool) -> None:
    """Run ingest_company in a background thread (own DB session)."""
    from src.etl.pipeline import ingest_company

    ingest_company(ticker, years=years, quarterly=quarterly)


# ── Endpoints ────────────────────────────────


@router.post("/ingest")
def trigger_ingest(body: IngestRequest, db: Session = Depends(get_db)):
    """Start a full company ingestion in a background thread."""
    ticker = body.ticker.upper().strip()

    # Create a preliminary EtlRun so the caller can track it
    etl_run = EtlRun(ticker=ticker, run_type="full_ingest", status="running")
    db.add(etl_run)
    db.commit()
    db.refresh(etl_run)

    thread = threading.Thread(
        target=_run_ingest,
        args=(ticker, body.years, body.quarterly),
        daemon=True,
    )
    thread.start()

    return {
        "message": f"Ingestion started for {ticker}",
        "etl_run_id": etl_run.id,
        "ticker": ticker,
    }


@router.post("/sync-prices")
def trigger_sync_prices(body: SyncPricesRequest):
    """Sync daily prices for given tickers (or all companies)."""
    from src.etl.pipeline import sync_prices

    result = sync_prices(tickers=body.tickers)
    return {"message": "Price sync completed", "results": result}


@router.get("/runs")
def list_runs(
    ticker: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Query EtlRun history with optional filters."""
    q = db.query(EtlRun)
    if ticker:
        q = q.filter(EtlRun.ticker == ticker.upper())
    if status:
        q = q.filter(EtlRun.status == status)
    q = q.order_by(EtlRun.started_at.desc()).limit(limit)
    return [_row_to_dict(r) for r in q.all()]


@router.get("/runs/{ticker}")
def get_latest_run(ticker: str, db: Session = Depends(get_db)):
    """Get the latest EtlRun for a ticker."""
    row = (
        db.query(EtlRun)
        .filter(EtlRun.ticker == ticker.upper())
        .order_by(EtlRun.started_at.desc())
        .first()
    )
    if not row:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"No ETL runs found for {ticker}")
    return _row_to_dict(row)
