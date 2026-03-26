"""Filings router — list SEC filings and stream filing content."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from pfs.api.deps import get_db
from pfs.services import filings as filing_svc

router = APIRouter(prefix="/api/filings", tags=["filings"])


@router.get("/{ticker}")
def list_filings(
    ticker: str,
    form_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List SEC filings for a company."""
    try:
        return filing_svc.list_filings(db, ticker, form_type=form_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/{filing_id}")
def get_filing(ticker: str, filing_id: int, db: Session = Depends(get_db)):
    """Get a single SEC filing by ID."""
    result = filing_svc.get_filing(db, ticker, filing_id)
    if not result:
        raise HTTPException(status_code=404, detail="Filing not found")
    return result


@router.get("/{ticker}/{filing_id}/content")
def get_filing_content(ticker: str, filing_id: int, db: Session = Depends(get_db)):
    """Stream the raw HTML of a filing.

    1. Try local file first (data/raw/<ticker>/<form>_<date>.htm)
    2. Fallback: proxy from SEC EDGAR via primary_doc_url
    3. 404 if neither available
    """
    try:
        result = filing_svc.get_filing_content(db, ticker, filing_id)
    except RuntimeError:
        raise HTTPException(status_code=502, detail="Failed to fetch from SEC EDGAR")

    if result is None:
        raise HTTPException(status_code=404, detail="Filing content not available")

    media_type, content = result
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
    )
