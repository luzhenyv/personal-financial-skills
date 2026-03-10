"""MCP Server — read-only data tools for Claude agent.

Run:
    uv run python -m src.mcp.server
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.config import settings
from src.db.models import (
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
    RevenueSegment,
    SecFiling,
)
from src.db.session import SessionLocal

mcp = FastMCP("personal-finance")


# ── Helpers ──────────────────────────────────────


def _row_to_dict(obj) -> dict[str, Any]:
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        # Convert non-JSON-native types
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        elif isinstance(val, __import__("decimal").Decimal):
            val = float(val)
        result[col.name] = val
    return result


def _get_session():
    return SessionLocal()


# ── Tools ────────────────────────────────────────


@mcp.tool()
def list_companies() -> list[dict[str, Any]]:
    """List all companies in the database with ticker and name."""
    session = _get_session()
    try:
        rows = session.query(Company).order_by(Company.ticker).all()
        return [{"ticker": r.ticker, "name": r.name, "sector": r.sector} for r in rows]
    finally:
        session.close()


@mcp.tool()
def get_company(ticker: str) -> dict[str, Any]:
    """Get full details for a single company by ticker."""
    session = _get_session()
    try:
        row = session.query(Company).filter(Company.ticker == ticker.upper()).first()
        if not row:
            return {"error": f"Company '{ticker}' not found"}
        return _row_to_dict(row)
    finally:
        session.close()


@mcp.tool()
def get_income_statements(
    ticker: str, years: int = 5, quarterly: bool = False
) -> list[dict[str, Any]]:
    """Get income statement data for a company."""
    session = _get_session()
    try:
        q = session.query(IncomeStatement).filter(IncomeStatement.ticker == ticker.upper())
        if not quarterly:
            q = q.filter(IncomeStatement.fiscal_quarter.is_(None))
        rows = q.order_by(IncomeStatement.fiscal_year.desc()).limit(years).all()
        return [_row_to_dict(r) for r in reversed(rows)]
    finally:
        session.close()


@mcp.tool()
def get_balance_sheets(
    ticker: str, years: int = 5, quarterly: bool = False
) -> list[dict[str, Any]]:
    """Get balance sheet data for a company."""
    session = _get_session()
    try:
        q = session.query(BalanceSheet).filter(BalanceSheet.ticker == ticker.upper())
        if not quarterly:
            q = q.filter(BalanceSheet.fiscal_quarter.is_(None))
        rows = q.order_by(BalanceSheet.fiscal_year.desc()).limit(years).all()
        return [_row_to_dict(r) for r in reversed(rows)]
    finally:
        session.close()


@mcp.tool()
def get_cash_flows(
    ticker: str, years: int = 5, quarterly: bool = False
) -> list[dict[str, Any]]:
    """Get cash flow statement data for a company."""
    session = _get_session()
    try:
        q = session.query(CashFlowStatement).filter(
            CashFlowStatement.ticker == ticker.upper()
        )
        if not quarterly:
            q = q.filter(CashFlowStatement.fiscal_quarter.is_(None))
        rows = q.order_by(CashFlowStatement.fiscal_year.desc()).limit(years).all()
        return [_row_to_dict(r) for r in reversed(rows)]
    finally:
        session.close()


@mcp.tool()
def get_financial_metrics(ticker: str) -> list[dict[str, Any]]:
    """Get computed financial metrics (margins, growth, returns) for a company."""
    session = _get_session()
    try:
        rows = (
            session.query(FinancialMetric)
            .filter(
                FinancialMetric.ticker == ticker.upper(),
                FinancialMetric.fiscal_quarter.is_(None),
            )
            .order_by(FinancialMetric.fiscal_year.desc())
            .all()
        )
        return [_row_to_dict(r) for r in reversed(rows)]
    finally:
        session.close()


@mcp.tool()
def get_prices(ticker: str, period: str = "1y") -> list[dict[str, Any]]:
    """Get daily price data for a company.

    Args:
        ticker: Stock ticker symbol.
        period: Time period — one of '1m', '3m', '6m', '1y', '2y', '5y'.
    """
    from datetime import date, timedelta

    session = _get_session()
    try:
        period_days = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730, "5y": 1825}
        days = period_days.get(period, 365)
        cutoff = date.today() - timedelta(days=days)

        rows = (
            session.query(DailyPrice)
            .filter(DailyPrice.ticker == ticker.upper(), DailyPrice.date >= cutoff)
            .order_by(DailyPrice.date)
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


@mcp.tool()
def get_revenue_segments(
    ticker: str, fiscal_year: int | None = None
) -> list[dict[str, Any]]:
    """Get revenue segment breakdown (product, geography, channel) for a company."""
    session = _get_session()
    try:
        q = session.query(RevenueSegment).filter(RevenueSegment.ticker == ticker.upper())
        if fiscal_year:
            q = q.filter(RevenueSegment.fiscal_year == fiscal_year)
        rows = q.order_by(RevenueSegment.fiscal_year, RevenueSegment.segment_type).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


@mcp.tool()
def list_filings(ticker: str, form_type: str | None = None) -> list[dict[str, Any]]:
    """List SEC filings for a company (metadata only, no content)."""
    session = _get_session()
    try:
        q = session.query(SecFiling).filter(SecFiling.ticker == ticker.upper())
        if form_type:
            q = q.filter(SecFiling.filing_type == form_type)
        rows = q.order_by(SecFiling.filing_date.desc()).all()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


@mcp.tool()
def get_filing_content(ticker: str, filing_id: int) -> str:
    """Get the raw HTML content of a SEC filing.

    Tries local file first, then proxies from SEC EDGAR.
    Returns HTML as a string, or an error message.
    """
    session = _get_session()
    try:
        row = (
            session.query(SecFiling)
            .filter(SecFiling.id == filing_id, SecFiling.ticker == ticker.upper())
            .first()
        )
        if not row:
            return "Error: Filing not found"

        # 1. Try local file
        if row.filing_type and row.reporting_date:
            report_date = row.reporting_date.strftime("%Y_%m")
            form = row.filing_type.replace("/", "-")
            filename = f"{form}_{report_date}.htm"
            local_path = settings.raw_dir / ticker.upper() / filename
            if local_path.exists():
                return local_path.read_text(encoding="utf-8", errors="replace")

        # 2. SEC EDGAR fallback
        if row.primary_doc_url:
            from src.etl.sec_client import _request_with_retry

            resp = _request_with_retry(row.primary_doc_url, timeout=90)
            return resp.text

        return "Error: Filing content not available"
    finally:
        session.close()


# ── Entrypoint ───────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
