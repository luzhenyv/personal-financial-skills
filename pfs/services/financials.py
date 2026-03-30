"""Financial data service — income statements, balance sheets, cash flows, metrics, prices, segments."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from pfs.db.models import (
    BalanceSheet,
    CashFlowStatement,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
    RevenueSegment,
    StockSplit,
)
from pfs.services.companies import _row_to_dict, require_company


def get_income_statements(
    db: Session,
    ticker: str,
    *,
    years: int = 5,
    quarterly: bool = False,
) -> list[dict[str, Any]]:
    """Return income statements for *ticker*."""
    ticker = ticker.upper()
    require_company(db, ticker)
    q = db.query(IncomeStatement).filter(IncomeStatement.ticker == ticker)
    if not quarterly:
        q = q.filter(IncomeStatement.fiscal_quarter.is_(None))
    rows = q.order_by(IncomeStatement.fiscal_year.desc()).limit(years).all()
    return [_row_to_dict(r) for r in reversed(rows)]


def get_balance_sheets(
    db: Session,
    ticker: str,
    *,
    years: int = 5,
    quarterly: bool = False,
) -> list[dict[str, Any]]:
    """Return balance sheets for *ticker*."""
    ticker = ticker.upper()
    require_company(db, ticker)
    q = db.query(BalanceSheet).filter(BalanceSheet.ticker == ticker)
    if not quarterly:
        q = q.filter(BalanceSheet.fiscal_quarter.is_(None))
    rows = q.order_by(BalanceSheet.fiscal_year.desc()).limit(years).all()
    return [_row_to_dict(r) for r in reversed(rows)]


def get_cash_flows(
    db: Session,
    ticker: str,
    *,
    years: int = 5,
    quarterly: bool = False,
) -> list[dict[str, Any]]:
    """Return cash flow statements for *ticker*."""
    ticker = ticker.upper()
    require_company(db, ticker)
    q = db.query(CashFlowStatement).filter(CashFlowStatement.ticker == ticker)
    if not quarterly:
        q = q.filter(CashFlowStatement.fiscal_quarter.is_(None))
    rows = q.order_by(CashFlowStatement.fiscal_year.desc()).limit(years).all()
    return [_row_to_dict(r) for r in reversed(rows)]


def get_metrics(db: Session, ticker: str) -> list[dict[str, Any]]:
    """Return computed financial metrics for *ticker*."""
    ticker = ticker.upper()
    require_company(db, ticker)
    rows = (
        db.query(FinancialMetric)
        .filter(FinancialMetric.ticker == ticker, FinancialMetric.fiscal_quarter.is_(None))
        .order_by(FinancialMetric.fiscal_year.desc())
        .all()
    )
    return [_row_to_dict(r) for r in reversed(rows)]


def get_prices(
    db: Session,
    ticker: str,
    *,
    start: date | None = None,
    end: date | None = None,
    period: str = "1y",
) -> list[dict[str, Any]]:
    """Return daily OHLCV prices for *ticker*."""
    ticker = ticker.upper()
    require_company(db, ticker)

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


def get_segments(
    db: Session,
    ticker: str,
    *,
    fiscal_year: int | None = None,
) -> list[dict[str, Any]]:
    """Return revenue segment data for *ticker*."""
    ticker = ticker.upper()
    require_company(db, ticker)
    q = db.query(RevenueSegment).filter(RevenueSegment.ticker == ticker)
    if fiscal_year:
        q = q.filter(RevenueSegment.fiscal_year == fiscal_year)
    rows = q.order_by(RevenueSegment.fiscal_year, RevenueSegment.segment_type).all()
    return [_row_to_dict(r) for r in rows]


def get_stock_splits(db: Session, ticker: str) -> list[dict[str, Any]]:
    """Return stock split history for *ticker*."""
    ticker = ticker.upper()
    require_company(db, ticker)
    rows = (
        db.query(StockSplit)
        .filter(StockSplit.ticker == ticker)
        .order_by(StockSplit.split_date)
        .all()
    )
    return [_row_to_dict(r) for r in rows]


def get_quarterly(
    db: Session,
    ticker: str,
    *,
    quarters: int = 8,
) -> list[dict[str, Any]]:
    """Return combined quarterly financials (income + balance sheet + cash flow).

    Each result dict merges the three statements for the same (fiscal_year, fiscal_quarter).
    Only rows with a non-null fiscal_quarter are included.
    """
    ticker = ticker.upper()
    require_company(db, ticker)

    income_rows = (
        db.query(IncomeStatement)
        .filter(IncomeStatement.ticker == ticker, IncomeStatement.fiscal_quarter.isnot(None))
        .order_by(IncomeStatement.fiscal_year.desc(), IncomeStatement.fiscal_quarter.desc())
        .limit(quarters)
        .all()
    )

    # Build lookup key → dict for balance sheets and cash flows
    bs_rows = (
        db.query(BalanceSheet)
        .filter(BalanceSheet.ticker == ticker, BalanceSheet.fiscal_quarter.isnot(None))
        .order_by(BalanceSheet.fiscal_year.desc(), BalanceSheet.fiscal_quarter.desc())
        .limit(quarters)
        .all()
    )
    cf_rows = (
        db.query(CashFlowStatement)
        .filter(CashFlowStatement.ticker == ticker, CashFlowStatement.fiscal_quarter.isnot(None))
        .order_by(CashFlowStatement.fiscal_year.desc(), CashFlowStatement.fiscal_quarter.desc())
        .limit(quarters)
        .all()
    )

    bs_map = {(r.fiscal_year, r.fiscal_quarter): _row_to_dict(r) for r in bs_rows}
    cf_map = {(r.fiscal_year, r.fiscal_quarter): _row_to_dict(r) for r in cf_rows}

    results = []
    for inc in reversed(income_rows):
        key = (inc.fiscal_year, inc.fiscal_quarter)
        merged: dict[str, Any] = {"source_type": "quarterly"}
        merged.update(_row_to_dict(inc))
        if key in bs_map:
            merged["balance_sheet"] = bs_map[key]
        if key in cf_map:
            merged["cash_flow"] = cf_map[key]
        results.append(merged)
    return results
