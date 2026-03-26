"""Companies router — list and lookup companies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pfs.api.deps import get_db
from pfs.services import companies as company_svc

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("/")
def list_companies(
    sector: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List all companies with optional sector filter."""
    return company_svc.list_companies(db, sector=sector, limit=limit, offset=offset)


@router.get("/{ticker}")
def get_company(ticker: str, db: Session = Depends(get_db)):
    """Get a single company by ticker."""
    result = company_svc.get_company(db, ticker)
    if not result:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")
    return result
