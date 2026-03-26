"""ETL orchestration service — trigger ingestion and query run history."""

from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from pfs.db.models import EtlRun


def _etl_row_to_dict(obj: Any) -> dict[str, Any]:
    """Convert an EtlRun instance to dict, handling column key mappings."""
    try:
        mapper = sa_inspect(type(obj))
        result = {}
        for col_attr in mapper.mapper.column_attrs:
            result[col_attr.key] = getattr(obj, col_attr.key)
        return result
    except Exception:
        # Fallback for mock/test objects that use __table__.columns directly
        result = {}
        for col in obj.__table__.columns:
            result[col.name] = getattr(obj, col.name)
        return result


def _run_ingest(ticker: str, years: int, quarterly: bool) -> None:
    """Run ingest_company in a background thread (own DB session)."""
    from pfs.etl.pipeline import ingest_company

    ingest_company(ticker, years=years, quarterly=quarterly)


def start_ingest(db: Session, ticker: str, years: int = 5, quarterly: bool = False) -> dict:
    """Create an EtlRun record and start ingestion in a background thread."""
    ticker = ticker.upper().strip()
    etl_run = EtlRun(ticker=ticker, run_type="full_ingest", status="running")
    db.add(etl_run)
    db.commit()
    db.refresh(etl_run)

    thread = threading.Thread(
        target=_run_ingest,
        args=(ticker, years, quarterly),
        daemon=True,
    )
    thread.start()

    return {
        "message": f"Ingestion started for {ticker}",
        "etl_run_id": etl_run.id,
        "ticker": ticker,
    }


def sync_prices(tickers: list[str] | None = None) -> dict:
    """Sync daily prices for given tickers (or all companies)."""
    from pfs.etl.pipeline import sync_prices as _sync

    result = _sync(tickers=tickers)
    return {"message": "Price sync completed", "results": result}


def list_runs(
    db: Session,
    *,
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Query EtlRun history with optional filters."""
    q = db.query(EtlRun)
    if ticker:
        q = q.filter(EtlRun.ticker == ticker.upper())
    if status:
        q = q.filter(EtlRun.status == status)
    q = q.order_by(EtlRun.started_at.desc()).limit(limit)
    return [_etl_row_to_dict(r) for r in q.all()]


def get_latest_run(db: Session, ticker: str) -> dict[str, Any] | None:
    """Return the latest EtlRun for *ticker*, or ``None``."""
    row = (
        db.query(EtlRun)
        .filter(EtlRun.ticker == ticker.upper())
        .order_by(EtlRun.started_at.desc())
        .first()
    )
    if not row:
        return None
    return _etl_row_to_dict(row)
