"""Companies router — list and lookup companies."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models import Company

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _row_to_dict(obj) -> dict[str, Any]:
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        result[col.name] = val
    return result


@router.get("/")
def list_companies(
    sector: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List all companies with optional sector filter."""
    q = db.query(Company)
    if sector:
        q = q.filter(Company.sector == sector)
    q = q.order_by(Company.ticker).offset(offset).limit(limit)
    return [_row_to_dict(c) for c in q.all()]


@router.get("/{ticker}")
def get_company(ticker: str, db: Session = Depends(get_db)):
    """Get a single company by ticker."""
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")
    return _row_to_dict(company)
