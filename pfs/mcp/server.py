"""MCP Server — data tools for Claude agent.

Run (stdio — local agent):
    uv run python -m pfs.mcp.server

Run (HTTP — remote agent on port 8001):
    uv run python -m pfs.mcp.server --http
    uv run python -m pfs.mcp.server --http --port 8001 --host 0.0.0.0
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pfs.config import settings
from pfs.db.models import (
    AnalysisReport,
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
    RevenueSegment,
    SecFiling,
    StockSplit,
)
from pfs.db.session import SessionLocal

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
            from pfs.etl.sec_client import _request_with_retry

            resp = _request_with_retry(row.primary_doc_url, timeout=90)
            return resp.text

        return "Error: Filing content not available"
    finally:
        session.close()


@mcp.tool()
def get_stock_splits(ticker: str) -> list[dict[str, Any]]:
    """Get stock split history for a company.

    Returns a list of splits sorted by date, each with 'date', 'ratio', and
    'source' fields.  Returns an empty list if no splits are recorded.
    """
    session = _get_session()
    try:
        rows = (
            session.query(StockSplit)
            .filter(StockSplit.ticker == ticker.upper())
            .order_by(StockSplit.split_date)
            .all()
        )
        return [
            {
                "date": str(row.split_date),
                "ratio": float(row.ratio),
                "source": row.source,
            }
            for row in rows
        ]
    finally:
        session.close()


@mcp.tool()
def get_annual_financials(ticker: str, years: int = 5) -> dict[str, Any]:
    """Get combined annual financial data with split-adjusted per-share metrics.

    Joins income statements, balance sheets, cash flows, and financial metrics
    into a single response.  EPS is automatically adjusted to the current share
    basis using the stock_splits table.

    Returns a dict with 'ticker', 'fiscal_year_end', and 'years' (list of
    annual records, oldest first).
    """
    from sqlalchemy import text as sa_text

    from pfs.services.splits import get_split_adjustor

    session = _get_session()
    try:
        # Resolve fiscal-year-end code for split adjustment
        company = session.query(Company).filter(Company.ticker == ticker.upper()).first()
        fye_code = company.fiscal_year_end if company else None

        rows = session.execute(sa_text("""
            SELECT
                i.fiscal_year,
                i.filing_date,
                i.revenue          / 1e9 AS rev_b,
                i.gross_profit     / 1e9 AS gp_b,
                i.operating_income / 1e9 AS oi_b,
                i.net_income       / 1e9 AS ni_b,
                i.eps_diluted,
                i.research_and_development / 1e9 AS rd_b,
                i.shares_diluted   / 1e9 AS shares_b,
                cf.free_cash_flow  / 1e9 AS fcf_b,
                cf.capital_expenditure / 1e9 AS capex_b,
                cf.stock_based_compensation / 1e9 AS sbc_b,
                cf.share_repurchase / 1e9 AS buyback_b,
                m.gross_margin     * 100 AS gm_pct,
                m.operating_margin * 100 AS om_pct,
                m.net_margin       * 100 AS nm_pct,
                m.fcf_margin       * 100 AS fcf_margin_pct,
                m.revenue_growth   * 100 AS rev_growth_pct,
                m.eps_growth       * 100 AS eps_growth_pct,
                m.roe  * 100 AS roe_pct,
                m.roa  * 100 AS roa_pct,
                m.roic * 100 AS roic_pct,
                m.current_ratio,
                m.debt_to_equity,
                m.pe_ratio,
                b.cash_and_equivalents    / 1e9 AS cash_b,
                b.short_term_investments  / 1e9 AS sti_b,
                b.accounts_receivable     / 1e9 AS ar_b,
                b.inventory               / 1e9 AS inv_b,
                b.total_current_assets    / 1e9 AS cur_assets_b,
                b.total_assets            / 1e9 AS assets_b,
                b.short_term_debt         / 1e9 AS std_b,
                b.long_term_debt          / 1e9 AS ltd_b,
                b.total_current_liabilities / 1e9 AS cur_liab_b,
                b.total_stockholders_equity / 1e9 AS equity_b
            FROM income_statements i
            JOIN financial_metrics m
                ON i.ticker = m.ticker AND i.fiscal_year = m.fiscal_year
                AND m.fiscal_quarter IS NULL
            JOIN cash_flow_statements cf
                ON i.ticker = cf.ticker AND i.fiscal_year = cf.fiscal_year
                AND cf.fiscal_quarter IS NULL
            JOIN balance_sheets b
                ON i.ticker = b.ticker AND i.fiscal_year = b.fiscal_year
                AND b.fiscal_quarter IS NULL
            WHERE i.ticker = :ticker AND i.fiscal_quarter IS NULL
            ORDER BY i.fiscal_year DESC
            LIMIT :years
        """), {"ticker": ticker.upper(), "years": years}).mappings().all()

        results = [dict(r) for r in reversed(rows)]

        # Split-adjust per-share metrics
        adjust = get_split_adjustor(ticker.upper(), fiscal_year_end=fye_code, db=session)
        for d in results:
            fy = d.get("fiscal_year")
            if fy is not None:
                d["eps_diluted"] = adjust(fy, d.get("eps_diluted"))
            # Convert any remaining non-JSON-native types
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
                elif isinstance(v, __import__("decimal").Decimal):
                    d[k] = float(v)

        return {
            "ticker": ticker.upper(),
            "fiscal_year_end": fye_code,
            "years": results,
        }
    finally:
        session.close()


@mcp.tool()
def save_analysis_report(
    ticker: str,
    report_type: str,
    title: str,
    content_md: str,
    file_path: str,
) -> dict[str, Any]:
    """Upsert an analysis report into the database.

    Replaces any existing report with the same ticker + report_type.

    Args:
        ticker: Stock ticker symbol.
        report_type: Report category, e.g. 'company_profile'.
        title: Human-readable report title.
        content_md: Full markdown content of the report.
        file_path: Filesystem path where the report is also saved.
    """
    session = _get_session()
    try:
        session.query(AnalysisReport).filter(
            AnalysisReport.ticker == ticker.upper(),
            AnalysisReport.report_type == report_type,
        ).delete()

        report = AnalysisReport(
            ticker=ticker.upper(),
            report_type=report_type,
            title=title,
            content_md=content_md,
            generated_by="claude",
            file_path=file_path,
        )
        session.add(report)
        session.commit()
        return {"status": "ok", "ticker": ticker.upper(), "report_type": report_type}
    except Exception as e:
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


# ── Entrypoint ───────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PFS MCP Server")
    parser.add_argument("--http", action="store_true", help="Use streamable-http transport")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="HTTP bind port (default: 8001)")
    args = parser.parse_args()

    if args.http:
        from mcp.server.fastmcp.server import TransportSecuritySettings
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        # Disable DNS-rebinding protection — the MCP server is only reachable
        # over the private Tailscale WireGuard tunnel (not exposed to internet).
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
