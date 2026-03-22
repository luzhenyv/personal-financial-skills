"""Company profile data access layer.

Queries PostgreSQL and returns structured dicts for the Streamlit data loader.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
    from pfs.db.session import get_session
    from pfs.db.models import (
        Company,
        IncomeStatement,
        BalanceSheet,
        CashFlowStatement,
        FinancialMetric,
        DailyPrice,
    )

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


def generate_tearsheet(ticker: str) -> str:
    """Generate a concise markdown tearsheet for *ticker*.

    Pulls from artifact JSON files (``data/artifacts/<ticker>/``) and the
    database.  Any missing data source is skipped gracefully.

    Args:
        ticker: Upper-case ticker symbol, e.g. ``"NVDA"``.

    Returns:
        A markdown string suitable for display or download.
    """
    processed_dir = Path("data/artifacts") / ticker

    def _load(filename: str) -> dict[str, Any] | list | None:
        path = processed_dir / filename
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    overview: dict = _load("company_overview.json") or {}
    thesis: dict = _load("investment_thesis.json") or {}
    comps: dict = _load("comps_table.json") or {}
    risks_data: dict = _load("risk_factors.json") or {}

    # DB lookup for latest financials
    profile = get_profile_data(ticker, years=1)
    latest_income = (profile.get("income_statements") or [{}])[-1]
    latest_metrics = (profile.get("metrics") or [{}])[-1]
    company_db = profile.get("company") or {}
    latest_price_db = profile.get("latest_price") or {}

    lines: list[str] = []

    # Header
    company_name = overview.get("company_name") or company_db.get("name") or ticker
    fy = overview.get("fiscal_year", "")
    lines.append(f"# {company_name} ({ticker}) — Tearsheet")
    if fy:
        lines.append(f"*Fiscal Year {fy} | Generated {__import__('datetime').date.today()}*")
    lines.append("")

    # Business summary
    description = overview.get("description") or overview.get("business_overview", "")
    if description:
        lines.append("## Business Summary")
        lines.append(description)
        lines.append("")

    # Key financials
    revenue = latest_income.get("revenue")
    net_income = latest_income.get("net_income")
    gross_margin = latest_metrics.get("gross_margin_pct")
    op_margin = latest_metrics.get("operating_margin_pct")
    net_margin = latest_metrics.get("net_margin_pct")
    pe_fwd = latest_metrics.get("pe_forward") or latest_metrics.get("pe_ratio")
    ev_ebitda = latest_metrics.get("ev_ebitda")
    price = latest_price_db.get("close") or latest_price_db.get("price")

    fin_rows = []
    if revenue is not None:
        fin_rows.append(f"| Revenue | ${revenue / 1e9:.1f}B |")
    if net_income is not None:
        fin_rows.append(f"| Net Income | ${net_income / 1e9:.1f}B |")
    if gross_margin is not None:
        fin_rows.append(f"| Gross Margin | {gross_margin:.1f}% |")
    if op_margin is not None:
        fin_rows.append(f"| Operating Margin | {op_margin:.1f}% |")
    if net_margin is not None:
        fin_rows.append(f"| Net Margin | {net_margin:.1f}% |")
    if pe_fwd is not None:
        fin_rows.append(f"| Fwd P/E | {pe_fwd:.1f}x |")
    if ev_ebitda is not None:
        fin_rows.append(f"| EV/EBITDA | {ev_ebitda:.1f}x |")
    if price is not None:
        fin_rows.append(f"| Stock Price | ${price:.2f} |")

    if fin_rows:
        lines.append("## Key Financials")
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        lines.extend(fin_rows)
        lines.append("")

    # Bull case (top 3 points)
    bull_items: list[dict] = thesis.get("bull_case", [])
    if bull_items:
        lines.append("## Investment Thesis (Bull Case)")
        for item in bull_items[:3]:
            title = item.get("title", "")
            desc = item.get("description", "")
            if title:
                lines.append(f"**{title}**")
                if desc:
                    lines.append(desc)
                lines.append("")

    # Key risks (top 3)
    risk_items: list[dict] = risks_data.get("risks", [])
    if risk_items:
        lines.append("## Key Risks")
        for risk in risk_items[:3]:
            risk_title = risk.get("title") or risk.get("risk") or risk.get("name", "")
            risk_desc = risk.get("description") or risk.get("detail", "")
            if risk_title:
                lines.append(f"- **{risk_title}**: {risk_desc}" if risk_desc else f"- {risk_title}")
        lines.append("")

    # Comps summary (top 4 peers)
    peers: list[dict] = comps.get("peers", [])
    if peers:
        lines.append("## Comparable Companies")
        lines.append("| Ticker | Market Cap | Rev Growth | Gross Margin | Fwd P/E | EV/EBITDA |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for p in peers[:4]:
            t = p.get("ticker", "")
            mc = f"${p['market_cap_b']:.0f}B" if p.get("market_cap_b") is not None else "—"
            rg = f"{p['rev_growth_pct']:.1f}%" if p.get("rev_growth_pct") is not None else "—"
            gm = f"{p['gross_margin_pct']:.1f}%" if p.get("gross_margin_pct") is not None else "—"
            pe = f"{p['pe_forward']:.1f}x" if p.get("pe_forward") is not None else "—"
            ev = f"{p['ev_ebitda']:.1f}x" if p.get("ev_ebitda") is not None else "—"
            lines.append(f"| {t} | {mc} | {rg} | {gm} | {pe} | {ev} |")
        lines.append("")

    lines.append("---")
    lines.append("*This tearsheet is generated from SEC filings and market data. Not investment advice.*")

    return "\n".join(lines)
