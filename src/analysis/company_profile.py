"""Company Profile / Tearsheet generator.

Queries PostgreSQL for financial data and produces a markdown tearsheet.
Adapted from equity-research/skills/initiating-coverage in financial-services-plugins.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import (
    AnalysisReport,
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
)
from src.db.session import get_session
from src.etl.yfinance_client import get_current_price, get_stock_info

logger = logging.getLogger(__name__)


def _fmt_billions(val: int | None) -> str:
    """Format a value in billions with 1 decimal."""
    if val is None:
        return "N/A"
    b = val / 1_000_000_000
    if abs(b) >= 1:
        return f"{b:,.1f}"
    # Use millions for smaller values
    m = val / 1_000_000
    return f"{m:,.0f}M"


def _fmt_pct(val: float | None, multiplier: float = 100) -> str:
    """Format a ratio as percentage string."""
    if val is None:
        return "N/A"
    pct = float(val) * multiplier
    return f"{pct:+.1f}%" if multiplier == 100 else f"{pct:.1f}%"


def _fmt_margin(val: float | None) -> str:
    """Format margin as percentage (already a ratio 0-1)."""
    if val is None:
        return "N/A"
    return f"{float(val) * 100:.1f}%"


def _fmt_growth(val: float | None) -> str:
    """Format growth with arrow."""
    if val is None:
        return "N/A"
    pct = float(val) * 100
    arrow = "↑" if pct > 0 else "↓" if pct < 0 else "→"
    return f"{pct:+.1f}%{arrow}"


def _fmt_ratio(val: float | None) -> str:
    """Format a ratio like P/E, current ratio."""
    if val is None:
        return "N/A"
    return f"{float(val):.1f}x"


def _fmt_eps(val: float | None) -> str:
    """Format EPS."""
    if val is None:
        return "N/A"
    return f"${float(val):.2f}"


def _trend(values: list[float | None]) -> str:
    """Determine trend from a list of values (newest first)."""
    clean = [float(v) for v in values if v is not None]
    if len(clean) < 2:
        return "—"
    if clean[0] > clean[-1]:
        return "📈 Improving"
    elif clean[0] < clean[-1]:
        return "📉 Declining"
    return "→ Stable"


def _avg(values: list[float | None]) -> str:
    """Average of non-None values, formatted as margin."""
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return "N/A"
    return f"{sum(clean) / len(clean) * 100:.1f}%"


# ──────────────────────────────────────────────
# Data Loaders
# ──────────────────────────────────────────────

def load_company(session: Session, ticker: str) -> Company | None:
    return session.query(Company).filter_by(ticker=ticker.upper()).first()


def load_income_statements(session: Session, ticker: str, limit: int = 5) -> list[IncomeStatement]:
    return (
        session.query(IncomeStatement)
        .filter_by(ticker=ticker.upper(), fiscal_quarter=None)
        .order_by(desc(IncomeStatement.fiscal_year))
        .limit(limit)
        .all()
    )


def load_balance_sheets(session: Session, ticker: str, limit: int = 5) -> list[BalanceSheet]:
    return (
        session.query(BalanceSheet)
        .filter_by(ticker=ticker.upper(), fiscal_quarter=None)
        .order_by(desc(BalanceSheet.fiscal_year))
        .limit(limit)
        .all()
    )


def load_cash_flows(session: Session, ticker: str, limit: int = 5) -> list[CashFlowStatement]:
    return (
        session.query(CashFlowStatement)
        .filter_by(ticker=ticker.upper(), fiscal_quarter=None)
        .order_by(desc(CashFlowStatement.fiscal_year))
        .limit(limit)
        .all()
    )


def load_metrics(session: Session, ticker: str, limit: int = 5) -> list[FinancialMetric]:
    return (
        session.query(FinancialMetric)
        .filter_by(ticker=ticker.upper(), fiscal_quarter=None)
        .order_by(desc(FinancialMetric.fiscal_year))
        .limit(limit)
        .all()
    )


def load_latest_price(session: Session, ticker: str) -> DailyPrice | None:
    return (
        session.query(DailyPrice)
        .filter_by(ticker=ticker.upper())
        .order_by(desc(DailyPrice.date))
        .first()
    )


# ──────────────────────────────────────────────
# Tearsheet Generator
# ──────────────────────────────────────────────

def generate_tearsheet(
    ticker: str,
    session: Session | None = None,
    save: bool = True,
) -> str:
    """Generate a markdown tearsheet for a company.

    Args:
        ticker: Stock ticker symbol
        session: Optional DB session
        save: Whether to save to file and database

    Returns:
        Markdown string of the tearsheet
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        # Load data
        company = load_company(session, ticker)
        if not company:
            return f"# Error: Company {ticker} not found in database\n\nRun the financial-etl skill first:\n```python\nfrom src.etl.pipeline import ingest_company\ningest_company('{ticker}')\n```"

        incomes = load_income_statements(session, ticker)
        balances = load_balance_sheets(session, ticker)
        cash_flows = load_cash_flows(session, ticker)
        metrics = load_metrics(session, ticker)
        latest_price = load_latest_price(session, ticker)

        if not incomes:
            return f"# Error: No financial data for {ticker}\n\nRun ETL first."

        # Build the tearsheet
        md = _build_tearsheet(company, incomes, balances, cash_flows, metrics, latest_price)

        # Save
        if save:
            _save_tearsheet(session, ticker, company.name, md)
            if own_session:
                session.commit()

        return md

    finally:
        if own_session:
            session.close()


def _build_tearsheet(
    company: Company,
    incomes: list[IncomeStatement],
    balances: list[BalanceSheet],
    cash_flows: list[CashFlowStatement],
    metrics: list[FinancialMetric],
    latest_price: DailyPrice | None,
) -> str:
    """Build the full markdown tearsheet."""
    lines: list[str] = []

    # ── Header ──
    price_str = f"${float(latest_price.adjusted_close):.2f}" if latest_price else "N/A"
    mkt_cap_str = f"${company.market_cap / 1e9:.1f}B" if company.market_cap else "N/A"
    date_str = str(latest_price.date) if latest_price else datetime.now().strftime("%Y-%m-%d")

    # Fallback to yfinance for live price/market data if DB has no prices
    if not latest_price:
        try:
            yf_price = get_current_price(company.ticker)
            if yf_price:
                price_str = f"${yf_price:.2f}"
                date_str = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            pass

    lines.append(f"# {company.name} ({company.ticker}) — Tearsheet\n")
    lines.append(
        f"**Sector**: {company.sector or 'N/A'} | "
        f"**Industry**: {company.industry or 'N/A'} | "
        f"**Exchange**: {company.exchange or 'N/A'}"
    )
    lines.append(
        f"**Last Price**: {price_str} | "
        f"**Market Cap**: {mkt_cap_str} | "
        f"**Updated**: {date_str}\n"
    )

    # ── Business Summary ──
    lines.append("---\n")
    lines.append("## Business Summary\n")
    desc = company.description or f"{company.name} is a publicly traded company (SIC: {company.sic_code or 'N/A'})."
    lines.append(f"{desc}\n")

    # ── Key Financial Metrics ──
    lines.append("---\n")
    lines.append("## Key Financial Metrics\n")

    # Build header
    years = [str(inc.fiscal_year) for inc in incomes]
    header = "| Metric | " + " | ".join(f"FY{y}" for y in years) + " |"
    sep = "|--------|" + "|".join("--------" for _ in years) + "|"
    lines.append(header)
    lines.append(sep)

    # Revenue
    revs = [inc.revenue for inc in incomes]
    lines.append("| **Revenue** | " + " | ".join(f"${_fmt_billions(r)}" for r in revs) + " |")

    # Revenue Growth
    if metrics:
        growths = [m.revenue_growth for m in metrics]
        lines.append("| Revenue Growth | " + " | ".join(_fmt_growth(g) for g in growths) + " |")

    # Gross Profit
    gps = [inc.gross_profit for inc in incomes]
    lines.append("| **Gross Profit** | " + " | ".join(f"${_fmt_billions(g)}" for g in gps) + " |")

    # Operating Income
    ois = [inc.operating_income for inc in incomes]
    lines.append("| **Operating Income** | " + " | ".join(f"${_fmt_billions(o)}" for o in ois) + " |")

    # Net Income
    nis = [inc.net_income for inc in incomes]
    lines.append("| **Net Income** | " + " | ".join(f"${_fmt_billions(n)}" for n in nis) + " |")

    # EPS
    epss = [inc.eps_diluted for inc in incomes]
    lines.append("| **EPS (Diluted)** | " + " | ".join(_fmt_eps(e) for e in epss) + " |")

    # FCF
    fcfs = [cf.free_cash_flow for cf in cash_flows] if cash_flows else []
    if fcfs:
        lines.append("| **Free Cash Flow** | " + " | ".join(f"${_fmt_billions(f)}" for f in fcfs) + " |")

    lines.append("")

    # ── Margin Analysis ──
    if metrics and len(metrics) >= 2:
        lines.append("---\n")
        lines.append("## Margin Analysis\n")

        m_years = [str(m.fiscal_year) for m in metrics[:3]]
        m_header = "| Margin | " + " | ".join(f"FY{y}" for y in m_years) + " | 3Y Avg | Trend |"
        m_sep = "|--------|" + "|".join("--------" for _ in m_years) + "|--------|-------|"
        lines.append(m_header)
        lines.append(m_sep)

        gms = [m.gross_margin for m in metrics[:3]]
        lines.append(
            "| Gross Margin | " + " | ".join(_fmt_margin(g) for g in gms) +
            f" | {_avg(gms)} | {_trend(gms)} |"
        )

        oms = [m.operating_margin for m in metrics[:3]]
        lines.append(
            "| Operating Margin | " + " | ".join(_fmt_margin(o) for o in oms) +
            f" | {_avg(oms)} | {_trend(oms)} |"
        )

        nms = [m.net_margin for m in metrics[:3]]
        lines.append(
            "| Net Margin | " + " | ".join(_fmt_margin(n) for n in nms) +
            f" | {_avg(nms)} | {_trend(nms)} |"
        )

        fms = [m.fcf_margin for m in metrics[:3]]
        lines.append(
            "| FCF Margin | " + " | ".join(_fmt_margin(f) for f in fms) +
            f" | {_avg(fms)} | {_trend(fms)} |"
        )
        lines.append("")

    # ── Balance Sheet Snapshot ──
    if balances:
        bs = balances[0]  # Most recent
        lines.append("---\n")
        lines.append(f"## Balance Sheet Snapshot (FY{bs.fiscal_year})\n")
        lines.append("| Item | Value |")
        lines.append("|------|-------|")
        lines.append(f"| Cash & Equivalents | ${_fmt_billions(bs.cash_and_equivalents)} |")
        lines.append(f"| Total Current Assets | ${_fmt_billions(bs.total_current_assets)} |")
        lines.append(f"| Total Assets | ${_fmt_billions(bs.total_assets)} |")
        lines.append(f"| Total Current Liabilities | ${_fmt_billions(bs.total_current_liabilities)} |")
        lines.append(f"| Long-Term Debt | ${_fmt_billions(bs.long_term_debt)} |")
        lines.append(f"| Total Stockholders' Equity | ${_fmt_billions(bs.total_stockholders_equity)} |")

        if metrics:
            m0 = metrics[0]
            lines.append(f"| Current Ratio | {_fmt_ratio(m0.current_ratio)} |")
            lines.append(f"| Debt/Equity | {_fmt_ratio(m0.debt_to_equity)} |")
        lines.append("")

    # ── Returns & Efficiency ──
    if metrics and len(metrics) >= 2:
        lines.append("---\n")
        lines.append("## Returns & Efficiency\n")

        r_years = [str(m.fiscal_year) for m in metrics[:3]]
        r_header = "| Metric | " + " | ".join(f"FY{y}" for y in r_years) + " |"
        r_sep = "|--------|" + "|".join("--------" for _ in r_years) + "|"
        lines.append(r_header)
        lines.append(r_sep)

        roes = [m.roe for m in metrics[:3]]
        lines.append("| ROE | " + " | ".join(_fmt_margin(r) for r in roes) + " |")

        roas = [m.roa for m in metrics[:3]]
        lines.append("| ROA | " + " | ".join(_fmt_margin(r) for r in roas) + " |")

        roics = [m.roic for m in metrics[:3]]
        lines.append("| ROIC | " + " | ".join(_fmt_margin(r) for r in roics) + " |")
        lines.append("")

    # ── Valuation ──
    if metrics and latest_price:
        m0 = metrics[0]
        lines.append("---\n")
        lines.append("## Valuation\n")
        lines.append("| Multiple | Current |")
        lines.append("|----------|---------|")
        lines.append(f"| P/E | {_fmt_ratio(m0.pe_ratio)} |")
        lines.append(f"| P/S | {_fmt_ratio(m0.ps_ratio)} |")
        lines.append(f"| P/B | {_fmt_ratio(m0.pb_ratio)} |")
        lines.append(f"| EV/EBITDA | {_fmt_ratio(m0.ev_to_ebitda)} |")
        lines.append(f"| FCF Yield | {_fmt_margin(m0.fcf_yield)} |")
        lines.append("")

    # ── Footer ──
    lines.append("---\n")
    lines.append("## Investment Thesis (Bull Case)\n")
    lines.append("*To be filled by agent based on company analysis*\n")
    lines.append("- \n- \n- \n")

    lines.append("## Key Risks (Bear Case)\n")
    lines.append("*To be filled by agent based on company analysis*\n")
    lines.append("- \n- \n- \n")

    lines.append("## Near-Term Catalysts\n")
    lines.append("*To be filled by agent based on upcoming events*\n")
    lines.append("- \n- \n")

    lines.append("---\n")
    gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(
        f"*Generated on {gen_date} | Data source: SEC EDGAR XBRL | "
        f"View interactive dashboard: http://localhost:8501*"
    )

    return "\n".join(lines)


def _save_tearsheet(session: Session, ticker: str, name: str, content: str) -> None:
    """Save tearsheet to file and database."""
    # Save to file
    report_dir = settings.reports_dir / ticker
    report_dir.mkdir(parents=True, exist_ok=True)
    file_path = report_dir / "tearsheet.md"
    file_path.write_text(content, encoding="utf-8")
    logger.info(f"Saved tearsheet to {file_path}")

    # Save to database
    existing = (
        session.query(AnalysisReport)
        .filter_by(ticker=ticker, report_type="tearsheet")
        .first()
    )

    if existing:
        existing.content_md = content
        existing.title = f"{name} Tearsheet"
        existing.file_path = str(file_path)
        existing.created_at = datetime.utcnow()
    else:
        report = AnalysisReport(
            ticker=ticker,
            report_type="tearsheet",
            title=f"{name} Tearsheet",
            content_md=content,
            generated_by="system",
            file_path=str(file_path),
        )
        session.add(report)

    session.flush()


# ──────────────────────────────────────────────
# Data summary for API / Streamlit
# ──────────────────────────────────────────────

def get_profile_data(ticker: str, session: Session | None = None) -> dict[str, Any]:
    """Get structured profile data (for API/Streamlit, not markdown).

    Returns a dict with all the data needed to render a company profile.
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        company = load_company(session, ticker)
        if not company:
            return {"error": f"Company {ticker} not found"}

        incomes = load_income_statements(session, ticker)
        balances = load_balance_sheets(session, ticker)
        cash_flows = load_cash_flows(session, ticker)
        metrics_list = load_metrics(session, ticker)
        latest_price = load_latest_price(session, ticker)

        return {
            "company": {
                "ticker": company.ticker,
                "name": company.name,
                "cik": company.cik,
                "sector": company.sector,
                "industry": company.industry,
                "exchange": company.exchange,
                "sic_code": company.sic_code,
                "description": company.description,
                "website": company.website,
                "fiscal_year_end": company.fiscal_year_end,
                "market_cap": company.market_cap,
            },
            "income_statements": [
                {
                    "fiscal_year": inc.fiscal_year,
                    "revenue": inc.revenue,
                    "cost_of_revenue": inc.cost_of_revenue,
                    "gross_profit": inc.gross_profit,
                    "operating_income": inc.operating_income,
                    "net_income": inc.net_income,
                    "eps_diluted": float(inc.eps_diluted) if inc.eps_diluted else None,
                    "shares_diluted": inc.shares_diluted,
                    "research_and_development": inc.research_and_development,
                    "selling_general_admin": inc.selling_general_admin,
                }
                for inc in incomes
            ],
            "balance_sheets": [
                {
                    "fiscal_year": bs.fiscal_year,
                    "cash_and_equivalents": bs.cash_and_equivalents,
                    "total_current_assets": bs.total_current_assets,
                    "total_assets": bs.total_assets,
                    "total_current_liabilities": bs.total_current_liabilities,
                    "long_term_debt": bs.long_term_debt,
                    "total_liabilities": bs.total_liabilities,
                    "total_stockholders_equity": bs.total_stockholders_equity,
                }
                for bs in balances
            ],
            "cash_flows": [
                {
                    "fiscal_year": cf.fiscal_year,
                    "cash_from_operations": cf.cash_from_operations,
                    "capital_expenditure": cf.capital_expenditure,
                    "free_cash_flow": cf.free_cash_flow,
                    "cash_from_investing": cf.cash_from_investing,
                    "cash_from_financing": cf.cash_from_financing,
                }
                for cf in cash_flows
            ],
            "metrics": [
                {
                    "fiscal_year": m.fiscal_year,
                    "gross_margin": float(m.gross_margin) if m.gross_margin else None,
                    "operating_margin": float(m.operating_margin) if m.operating_margin else None,
                    "net_margin": float(m.net_margin) if m.net_margin else None,
                    "fcf_margin": float(m.fcf_margin) if m.fcf_margin else None,
                    "revenue_growth": float(m.revenue_growth) if m.revenue_growth else None,
                    "roe": float(m.roe) if m.roe else None,
                    "roa": float(m.roa) if m.roa else None,
                    "roic": float(m.roic) if m.roic else None,
                    "current_ratio": float(m.current_ratio) if m.current_ratio else None,
                    "debt_to_equity": float(m.debt_to_equity) if m.debt_to_equity else None,
                    "pe_ratio": float(m.pe_ratio) if m.pe_ratio else None,
                    "ps_ratio": float(m.ps_ratio) if m.ps_ratio else None,
                    "ev_to_ebitda": float(m.ev_to_ebitda) if m.ev_to_ebitda else None,
                    "fcf_yield": float(m.fcf_yield) if m.fcf_yield else None,
                }
                for m in metrics_list
            ],
            "latest_price": {
                "date": str(latest_price.date),
                "close": float(latest_price.close_price),
                "adjusted_close": float(latest_price.adjusted_close),
                "volume": latest_price.volume,
            } if latest_price else None,
        }

    finally:
        if own_session:
            session.close()
