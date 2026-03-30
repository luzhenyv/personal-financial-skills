"""Financials router — income statements, balance sheets, cash flows, metrics, prices, segments."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pfs.api.deps import get_db
from pfs.services import financials as fin_svc

router = APIRouter(prefix="/api/financials", tags=["financials"])


def _handle_value_error(e: ValueError) -> None:
    raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/income-statements")
def get_income_statements(
    ticker: str,
    years: int = Query(5, ge=1, le=20),
    quarterly: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        return fin_svc.get_income_statements(db, ticker, years=years, quarterly=quarterly)
    except ValueError as e:
        _handle_value_error(e)


@router.get("/{ticker}/balance-sheets")
def get_balance_sheets(
    ticker: str,
    years: int = Query(5, ge=1, le=20),
    quarterly: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        return fin_svc.get_balance_sheets(db, ticker, years=years, quarterly=quarterly)
    except ValueError as e:
        _handle_value_error(e)


@router.get("/{ticker}/cash-flows")
def get_cash_flows(
    ticker: str,
    years: int = Query(5, ge=1, le=20),
    quarterly: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        return fin_svc.get_cash_flows(db, ticker, years=years, quarterly=quarterly)
    except ValueError as e:
        _handle_value_error(e)


@router.get("/{ticker}/metrics")
def get_metrics(
    ticker: str,
    db: Session = Depends(get_db),
):
    try:
        return fin_svc.get_metrics(db, ticker)
    except ValueError as e:
        _handle_value_error(e)


@router.get("/{ticker}/prices")
def get_prices(
    ticker: str,
    start: date | None = Query(None),
    end: date | None = Query(None),
    period: str = Query("1y"),
    db: Session = Depends(get_db),
):
    try:
        return fin_svc.get_prices(db, ticker, start=start, end=end, period=period)
    except ValueError as e:
        _handle_value_error(e)


@router.get("/{ticker}/segments")
def get_segments(
    ticker: str,
    fiscal_year: int | None = Query(None),
    db: Session = Depends(get_db),
):
    try:
        return fin_svc.get_segments(db, ticker, fiscal_year=fiscal_year)
    except ValueError as e:
        _handle_value_error(e)


@router.get("/{ticker}/quarterly")
def get_quarterly(
    ticker: str,
    quarters: int = Query(8, ge=1, le=40),
    db: Session = Depends(get_db),
):
    """Return combined quarterly financials (income + balance sheet + cash flow)."""
    try:
        return fin_svc.get_quarterly(db, ticker, quarters=quarters)
    except ValueError as e:
        _handle_value_error(e)
