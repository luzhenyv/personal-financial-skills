"""Company profile data access layer.

Queries PostgreSQL and returns structured dicts for the Streamlit data loader.
"""

from __future__ import annotations

from typing import Any

from src.db.session import get_session
from src.db.models import (
    Company,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    FinancialMetric,
    DailyPrice,
)


def _row_to_dict(obj) -> dict[str, Any]:
    """Convert a SQLAlchemy model instance to a plain dict."""
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        result[col.name] = val
    return result


def get_profile_data(ticker: str, years: int = 7) -> dict[str, Any]:
    """Return all DB data needed for the Company Profile page.

    Args:
        ticker: Upper-case ticker symbol, e.g. ``"NVDA"``.
        years:  How many fiscal years of history to return.

    Returns:
        Dict with keys ``company``, ``income_statements``, ``balance_sheets``,
        ``cash_flows``, ``metrics``, ``latest_price``.
        Returns ``{"error": "..."}`` if the company is not found.
    """
    session = get_session()
    try:
        company = session.query(Company).filter(Company.ticker == ticker).first()
        if company is None:
            return {"error": f"Company '{ticker}' not found in database."}

        incomes = (
            session.query(IncomeStatement)
            .filter(
                IncomeStatement.ticker == ticker,
                IncomeStatement.fiscal_quarter.is_(None),
            )
            .order_by(IncomeStatement.fiscal_year.desc())
            .limit(years)
            .all()
        )

        balances = (
            session.query(BalanceSheet)
            .filter(
                BalanceSheet.ticker == ticker,
                BalanceSheet.fiscal_quarter.is_(None),
            )
            .order_by(BalanceSheet.fiscal_year.desc())
            .limit(years)
            .all()
        )

        cash_flows = (
            session.query(CashFlowStatement)
            .filter(
                CashFlowStatement.ticker == ticker,
                CashFlowStatement.fiscal_quarter.is_(None),
            )
            .order_by(CashFlowStatement.fiscal_year.desc())
            .limit(years)
            .all()
        )

        metrics = (
            session.query(FinancialMetric)
            .filter(
                FinancialMetric.ticker == ticker,
                FinancialMetric.fiscal_quarter.is_(None),
            )
            .order_by(FinancialMetric.fiscal_year.desc())
            .limit(years)
            .all()
        )

        latest_price = (
            session.query(DailyPrice)
            .filter(DailyPrice.ticker == ticker)
            .order_by(DailyPrice.date.desc())
            .first()
        )

        return {
            "company": _row_to_dict(company),
            "income_statements": [_row_to_dict(r) for r in reversed(incomes)],
            "balance_sheets": [_row_to_dict(r) for r in reversed(balances)],
            "cash_flows": [_row_to_dict(r) for r in reversed(cash_flows)],
            "metrics": [_row_to_dict(r) for r in reversed(metrics)],
            "latest_price": _row_to_dict(latest_price) if latest_price else None,
        }
    finally:
        session.close()
