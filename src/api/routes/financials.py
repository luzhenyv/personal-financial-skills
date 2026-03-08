"""Financial data routes — income statements, balance sheets, cash flows, metrics."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.db.models import (
    BalanceSheet,
    CashFlowStatement,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
    SecFiling,
)
from src.db.session import get_db

router = APIRouter()


@router.get("/{ticker}/income-statements")
def get_income_statements(
    ticker: str,
    limit: int = Query(5, ge=1, le=20),
    quarterly: bool = False,
    db: Session = Depends(get_db),
):
    """Get income statements for a company."""
    query = db.query(IncomeStatement).filter_by(ticker=ticker.upper())
    if not quarterly:
        query = query.filter(IncomeStatement.fiscal_quarter.is_(None))
    rows = query.order_by(desc(IncomeStatement.fiscal_year)).limit(limit).all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No income statements for {ticker}")

    return [
        {
            "fiscal_year": r.fiscal_year,
            "fiscal_quarter": r.fiscal_quarter,
            "revenue": r.revenue,
            "cost_of_revenue": r.cost_of_revenue,
            "gross_profit": r.gross_profit,
            "research_and_development": r.research_and_development,
            "selling_general_admin": r.selling_general_admin,
            "operating_expenses": r.operating_expenses,
            "operating_income": r.operating_income,
            "interest_expense": r.interest_expense,
            "interest_income": r.interest_income,
            "pretax_income": r.pretax_income,
            "income_tax": r.income_tax,
            "net_income": r.net_income,
            "eps_basic": float(r.eps_basic) if r.eps_basic else None,
            "eps_diluted": float(r.eps_diluted) if r.eps_diluted else None,
            "shares_basic": r.shares_basic,
            "shares_diluted": r.shares_diluted,
            "filing_type": r.filing_type,
        }
        for r in rows
    ]


@router.get("/{ticker}/balance-sheets")
def get_balance_sheets(
    ticker: str,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Get balance sheets for a company."""
    rows = (
        db.query(BalanceSheet)
        .filter_by(ticker=ticker.upper())
        .filter(BalanceSheet.fiscal_quarter.is_(None))
        .order_by(desc(BalanceSheet.fiscal_year))
        .limit(limit)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No balance sheets for {ticker}")

    return [
        {
            "fiscal_year": r.fiscal_year,
            "cash_and_equivalents": r.cash_and_equivalents,
            "short_term_investments": r.short_term_investments,
            "accounts_receivable": r.accounts_receivable,
            "inventory": r.inventory,
            "total_current_assets": r.total_current_assets,
            "property_plant_equipment": r.property_plant_equipment,
            "goodwill": r.goodwill,
            "intangible_assets": r.intangible_assets,
            "total_assets": r.total_assets,
            "accounts_payable": r.accounts_payable,
            "short_term_debt": r.short_term_debt,
            "total_current_liabilities": r.total_current_liabilities,
            "long_term_debt": r.long_term_debt,
            "total_liabilities": r.total_liabilities,
            "common_stock": r.common_stock,
            "retained_earnings": r.retained_earnings,
            "total_stockholders_equity": r.total_stockholders_equity,
        }
        for r in rows
    ]


@router.get("/{ticker}/cash-flows")
def get_cash_flows(
    ticker: str,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Get cash flow statements for a company."""
    rows = (
        db.query(CashFlowStatement)
        .filter_by(ticker=ticker.upper())
        .filter(CashFlowStatement.fiscal_quarter.is_(None))
        .order_by(desc(CashFlowStatement.fiscal_year))
        .limit(limit)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No cash flow statements for {ticker}")

    return [
        {
            "fiscal_year": r.fiscal_year,
            "net_income": r.net_income,
            "depreciation_amortization": r.depreciation_amortization,
            "stock_based_compensation": r.stock_based_compensation,
            "cash_from_operations": r.cash_from_operations,
            "capital_expenditure": r.capital_expenditure,
            "cash_from_investing": r.cash_from_investing,
            "cash_from_financing": r.cash_from_financing,
            "free_cash_flow": r.free_cash_flow,
            "net_change_in_cash": r.net_change_in_cash,
        }
        for r in rows
    ]


@router.get("/{ticker}/metrics")
def get_metrics(
    ticker: str,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Get computed financial metrics for a company."""
    rows = (
        db.query(FinancialMetric)
        .filter_by(ticker=ticker.upper())
        .filter(FinancialMetric.fiscal_quarter.is_(None))
        .order_by(desc(FinancialMetric.fiscal_year))
        .limit(limit)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No metrics for {ticker}")

    return [
        {
            "fiscal_year": r.fiscal_year,
            "gross_margin": float(r.gross_margin) if r.gross_margin else None,
            "operating_margin": float(r.operating_margin) if r.operating_margin else None,
            "net_margin": float(r.net_margin) if r.net_margin else None,
            "fcf_margin": float(r.fcf_margin) if r.fcf_margin else None,
            "revenue_growth": float(r.revenue_growth) if r.revenue_growth else None,
            "operating_income_growth": float(r.operating_income_growth) if r.operating_income_growth else None,
            "net_income_growth": float(r.net_income_growth) if r.net_income_growth else None,
            "eps_growth": float(r.eps_growth) if r.eps_growth else None,
            "roe": float(r.roe) if r.roe else None,
            "roa": float(r.roa) if r.roa else None,
            "roic": float(r.roic) if r.roic else None,
            "debt_to_equity": float(r.debt_to_equity) if r.debt_to_equity else None,
            "current_ratio": float(r.current_ratio) if r.current_ratio else None,
            "pe_ratio": float(r.pe_ratio) if r.pe_ratio else None,
            "ps_ratio": float(r.ps_ratio) if r.ps_ratio else None,
            "ev_to_ebitda": float(r.ev_to_ebitda) if r.ev_to_ebitda else None,
            "fcf_yield": float(r.fcf_yield) if r.fcf_yield else None,
        }
        for r in rows
    ]


@router.get("/{ticker}/prices")
def get_prices(
    ticker: str,
    limit: int = Query(30, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Get daily price data for a company."""
    rows = (
        db.query(DailyPrice)
        .filter_by(ticker=ticker.upper())
        .order_by(desc(DailyPrice.date))
        .limit(limit)
        .all()
    )

    return [
        {
            "date": str(r.date),
            "open": float(r.open_price) if r.open_price else None,
            "high": float(r.high_price) if r.high_price else None,
            "low": float(r.low_price) if r.low_price else None,
            "close": float(r.close_price) if r.close_price else None,
            "adjusted_close": float(r.adjusted_close) if r.adjusted_close else None,
            "volume": r.volume,
        }
        for r in rows
    ]


@router.get("/{ticker}/filings")
def get_filings(
    ticker: str,
    filing_type: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get SEC filing history for a company."""
    query = db.query(SecFiling).filter_by(ticker=ticker.upper())
    if filing_type:
        query = query.filter_by(filing_type=filing_type)
    rows = query.order_by(desc(SecFiling.filing_date)).limit(limit).all()

    return [
        {
            "accession_number": r.accession_number,
            "filing_type": r.filing_type,
            "filing_date": str(r.filing_date) if r.filing_date else None,
            "reporting_date": str(r.reporting_date) if r.reporting_date else None,
            "is_processed": r.is_processed,
        }
        for r in rows
    ]
