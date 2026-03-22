"""Filings router — list SEC filings and stream filing content."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from pfs.config import settings
from pfs.db.models import Company, SecFiling
from pfs.db.session import get_db

router = APIRouter(prefix="/api/filings", tags=["filings"])


def _row_to_dict(obj) -> dict[str, Any]:
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        result[col.name] = val
    return result


def _require_company(db: Session, ticker: str) -> None:
    exists = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")


def _local_filing_path(ticker: str, filing: SecFiling):
    """Reconstruct the local file path for a downloaded filing."""
    if not filing.filing_type or not filing.reporting_date:
        return None
    report_date = filing.reporting_date.strftime("%Y_%m")
    form = filing.filing_type.replace("/", "-")
    filename = f"{form}_{report_date}.htm"
    return settings.raw_dir / ticker / filename


@router.get("/{ticker}")
def list_filings(
    ticker: str,
    form_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List SEC filings for a company."""
    ticker = ticker.upper()
    _require_company(db, ticker)
    q = db.query(SecFiling).filter(SecFiling.ticker == ticker)
    if form_type:
        q = q.filter(SecFiling.filing_type == form_type)
    rows = q.order_by(SecFiling.filing_date.desc()).all()

    results = []
    for r in rows:
        d = _row_to_dict(r)
        local = _local_filing_path(ticker, r)
        d["local_path"] = str(local) if local and local.exists() else None
        results.append(d)
    return results


@router.get("/{ticker}/{filing_id}")
def get_filing(ticker: str, filing_id: int, db: Session = Depends(get_db)):
    """Get a single SEC filing by ID."""
    ticker = ticker.upper()
    row = (
        db.query(SecFiling)
        .filter(SecFiling.id == filing_id, SecFiling.ticker == ticker)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Filing not found")
    d = _row_to_dict(row)
    local = _local_filing_path(ticker, row)
    d["local_path"] = str(local) if local and local.exists() else None
    return d


@router.get("/{ticker}/{filing_id}/content")
def get_filing_content(ticker: str, filing_id: int, db: Session = Depends(get_db)):
    """Stream the raw HTML of a filing.

    1. Try local file first (data/raw/<ticker>/<form>_<date>.htm)
    2. Fallback: proxy from SEC EDGAR via primary_doc_url
    3. 404 if neither available
    """
    ticker = ticker.upper()
    row = (
        db.query(SecFiling)
        .filter(SecFiling.id == filing_id, SecFiling.ticker == ticker)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Filing not found")

    # 1. Local file
    local = _local_filing_path(ticker, row)
    if local and local.exists():
        return StreamingResponse(
            open(local, "rb"),  # noqa: SIM115
            media_type="text/html",
            headers={"Content-Disposition": f'inline; filename="{local.name}"'},
        )

    # 2. SEC EDGAR proxy
    if row.primary_doc_url:
        from pfs.etl.sec_client import _request_with_retry

        try:
            resp = _request_with_retry(row.primary_doc_url, timeout=90)
            return StreamingResponse(
                iter([resp.content]),
                media_type="text/html",
            )
        except Exception:
            raise HTTPException(status_code=502, detail="Failed to fetch from SEC EDGAR")

    raise HTTPException(status_code=404, detail="Filing content not available")
