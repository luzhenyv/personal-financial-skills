"""Financials router — income statements, balance sheets, cash flows, metrics, prices, segments."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models import (
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
    RevenueSegment,
)

router = APIRouter(prefix="/api/financials", tags=["financials"])


def _row_to_dict(obj) -> dict[str, Any]:
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        result[col.name] = val
    return result


def _require_company(db: Session, ticker: str) -> None:
    """Raise 404 if company not ingested."""
    exists = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")


@router.get("/{ticker}/income-statements")
def get_income_statements(
    ticker: str,
    years: int = Query(5, ge=1, le=20),
    quarterly: bool = Query(False),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    _require_company(db, ticker)
    q = db.query(IncomeStatement).filter(IncomeStatement.ticker == ticker)
    if not quarterly:
        q = q.filter(IncomeStatement.fiscal_quarter.is_(None))
    rows = q.order_by(IncomeStatement.fiscal_year.desc()).limit(years).all()
    return [_row_to_dict(r) for r in reversed(rows)]


@router.get("/{ticker}/balance-sheets")
def get_balance_sheets(
    ticker: str,
    years: int = Query(5, ge=1, le=20),
    quarterly: bool = Query(False),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    _require_company(db, ticker)
    q = db.query(BalanceSheet).filter(BalanceSheet.ticker == ticker)
    if not quarterly:
        q = q.filter(BalanceSheet.fiscal_quarter.is_(None))
    rows = q.order_by(BalanceSheet.fiscal_year.desc()).limit(years).all()
    return [_row_to_dict(r) for r in reversed(rows)]


@router.get("/{ticker}/cash-flows")
def get_cash_flows(
    ticker: str,
    years: int = Query(5, ge=1, le=20),
    quarterly: bool = Query(False),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    _require_company(db, ticker)
    q = db.query(CashFlowStatement).filter(CashFlowStatement.ticker == ticker)
    if not quarterly:
        q = q.filter(CashFlowStatement.fiscal_quarter.is_(None))
    rows = q.order_by(CashFlowStatement.fiscal_year.desc()).limit(years).all()
    return [_row_to_dict(r) for r in reversed(rows)]


@router.get("/{ticker}/metrics")
def get_metrics(
    ticker: str,
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    _require_company(db, ticker)
    rows = (
        db.query(FinancialMetric)
        .filter(FinancialMetric.ticker == ticker, FinancialMetric.fiscal_quarter.is_(None))
        .order_by(FinancialMetric.fiscal_year.desc())
        .all()
    )
    return [_row_to_dict(r) for r in reversed(rows)]


@router.get("/{ticker}/prices")
def get_prices(
    ticker: str,
    start: date | None = Query(None),
    end: date | None = Query(None),
    period: str = Query("1y"),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    _require_company(db, ticker)

    q = db.query(DailyPrice).filter(DailyPrice.ticker == ticker)

    if start:
        q = q.filter(DailyPrice.date >= start)
    elif period:
        period_days = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730, "5y": 1825}
        days = period_days.get(period, 365)
        q = q.filter(DailyPrice.date >= date.today() - timedelta(days=days))

    if end:
        q = q.filter(DailyPrice.date <= end)

    rows = q.order_by(DailyPrice.date).all()
    return [_row_to_dict(r) for r in rows]


@router.get("/{ticker}/segments")
def get_segments(
    ticker: str,
    fiscal_year: int | None = Query(None),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    _require_company(db, ticker)
    q = db.query(RevenueSegment).filter(RevenueSegment.ticker == ticker)
    if fiscal_year:
        q = q.filter(RevenueSegment.fiscal_year == fiscal_year)
    rows = q.order_by(RevenueSegment.fiscal_year, RevenueSegment.segment_type).all()
    return [_row_to_dict(r) for r in rows]
