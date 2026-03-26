"""Company data service — CRUD operations for company records."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from pfs.db.models import Company


def _row_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy model instance to a plain dict."""
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        result[col.name] = val
    return result


def list_companies(
    db: Session,
    *,
    sector: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return companies with optional sector filter."""
    q = db.query(Company)
    if sector:
        q = q.filter(Company.sector == sector)
    q = q.order_by(Company.ticker).offset(offset).limit(limit)
    return [_row_to_dict(c) for c in q.all()]


def get_company(db: Session, ticker: str) -> dict[str, Any] | None:
    """Return a single company by ticker, or ``None`` if not found."""
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not company:
        return None
    return _row_to_dict(company)


def require_company(db: Session, ticker: str) -> None:
    """Raise ``ValueError`` if *ticker* is not in the database."""
    exists = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not exists:
        raise ValueError(f"Company '{ticker}' not found")
