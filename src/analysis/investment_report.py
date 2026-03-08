"""Investment Report generator — produces a comprehensive markdown report.

Combines company profile data + valuation analysis into a single
actionable report for personal investors.

Adapted from equity-research/skills/initiating-coverage (Task 5)
in financial-services-plugins, simplified from 30-50 page DOCX to
5-8 page decision-focused markdown.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.analysis.company_profile import (
    _fmt_billions,
    _fmt_eps,
    _fmt_growth,
    _fmt_margin,
    _fmt_ratio,
    load_balance_sheets,
    load_cash_flows,
    load_company,
    load_income_statements,
    load_latest_price,
    load_metrics,
)
from src.analysis.valuation import (
    ValuationSummary,
    valuation_summary,
)
from src.config import settings
from src.db.models import AnalysisReport
from src.db.session import get_session
from src.etl.yfinance_client import get_current_price

logger = logging.getLogger(__name__)


def generate_investment_report(
    ticker: str,
    revenue_growth: float = 0.10,
    wacc: float = 0.10,
    session: Session | None = None,
    save: bool = True,
) -> str:
    """Generate a comprehensive investment report in markdown.

    This is the personal investor equivalent of the institutional
    initiating-coverage report. Instead of 30-50 pages, it produces
    a focused 5-8 page decision-oriented document.

    Args:
        ticker: Stock ticker symbol
        revenue_growth: Base case revenue growth rate for DCF
        wacc: Discount rate for DCF
        session: Optional DB session
        save: Whether to save to file and database

    Returns:
        Markdown string of the full report
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        # Load all data
        company = load_company(session, ticker)
        if not company:
            return f"# Error: Company {ticker} not found\n\nRun `financial-etl` first."

        incomes = load_income_statements(session, ticker, limit=5)
        balances = load_balance_sheets(session, ticker, limit=5)
        cash_flows = load_cash_flows(session, ticker, limit=5)
        metrics = load_metrics(session, ticker, limit=5)
        latest_price = load_latest_price(session, ticker)

        if not incomes:
            return f"# Error: No financial data for {ticker}\n\nRun ETL first."

        # Run valuation
        val = valuation_summary(ticker, revenue_growth=revenue_growth, wacc=wacc, session=session)

        # Build report
        sections = []
        sections.append(_section_header(company, latest_price, val))
        sections.append(_section_investment_rating(val))
        sections.append(_section_company_overview(company))
        sections.append(_section_financial_performance(incomes, metrics))
        sections.append(_section_balance_sheet(balances, metrics))
        sections.append(_section_cash_flow(cash_flows))
        sections.append(_section_valuation(val))
        sections.append(_section_scenarios(val))
        sections.append(_section_risks_and_catalysts(company, metrics))
        sections.append(_section_action_plan(val, latest_price))
        sections.append(_section_footer(ticker))

        md = "\n\n".join(s for s in sections if s)

        if save:
            _save_report(session, ticker, company.name, md, {
                "revenue_growth": revenue_growth,
                "wacc": wacc,
            })
            if own_session:
                session.commit()

        return md

    finally:
        if own_session:
            session.close()


# ──────────────────────────────────────────────
# Report Sections
# ──────────────────────────────────────────────


def _section_header(company, latest_price, val: ValuationSummary) -> str:
    price_str = f"${float(latest_price.adjusted_close):.2f}" if latest_price else "N/A"
    target_str = f"${val.target_price:.2f}" if val.target_price else "N/A"
    mkt_cap = f"${company.market_cap / 1e9:.1f}B" if company.market_cap else "N/A"
    date_str = datetime.now().strftime("%B %d, %Y")

    # Fallback to yfinance for live price if DB has no prices
    current_price_val = float(latest_price.adjusted_close) if latest_price else None
    if not latest_price:
        try:
            yf_price = get_current_price(company.ticker)
            if yf_price:
                price_str = f"${yf_price:.2f}"
                current_price_val = yf_price
        except Exception:
            pass

    # Compute upside using actual price
    if current_price_val and val.target_price:
        upside_pct = (val.target_price - current_price_val) / current_price_val
        upside_str = f"{upside_pct * 100:+.1f}%"
        val.upside_pct = upside_pct
        val.current_price = current_price_val  # Store for later use
        # Update recommendation based on actual price
        if upside_pct > 0.15:
            val.recommendation = "BUY"
        elif upside_pct < -0.10:
            val.recommendation = "SELL"
        else:
            val.recommendation = "HOLD"
    else:
        upside_str = f"{val.upside_pct * 100:+.1f}%" if val.upside_pct is not None else "N/A"

    return f"""# {company.name} ({company.ticker}) — Investment Research Report

| | |
|---|---|
| **Current Price** | {price_str} |
| **Target Price** | {target_str} |
| **Upside/Downside** | {upside_str} |
| **Rating** | **{val.recommendation}** |
| **Market Cap** | {mkt_cap} |
| **Sector** | {company.sector or 'N/A'} |
| **Exchange** | {company.exchange or 'N/A'} |

*Report generated: {date_str} | Data source: SEC EDGAR XBRL*"""


def _section_investment_rating(val: ValuationSummary) -> str:
    lines = ["## Investment Rating\n"]

    if val.recommendation == "BUY":
        emoji = "🟢"
        desc = "The stock appears undervalued relative to our estimated intrinsic value."
    elif val.recommendation == "SELL":
        emoji = "🔴"
        desc = "The stock appears overvalued relative to our estimated intrinsic value."
    else:
        emoji = "🟡"
        desc = "The stock appears fairly valued at current levels."

    lines.append(f"### {emoji} {val.recommendation}\n")
    lines.append(desc)

    if val.target_price:
        lines.append(f"\n**Target Price: ${val.target_price:.2f}**")
    if val.upside_pct is not None:
        lines.append(f"**Expected Return: {val.upside_pct * 100:+.1f}%**\n")

    # Method breakdown
    if val.dcf:
        lines.append(f"- DCF Implied Price: ${val.dcf.implied_price:.2f}")
    if val.comps and val.comps.median_implied_price:
        lines.append(f"- Peer Comps Implied: ${val.comps.median_implied_price:.2f}")
    if val.scenarios and "base" in val.scenarios.scenarios:
        lines.append(f"- Base Scenario: ${val.scenarios.scenarios['base']['implied_price']:.2f}")

    return "\n".join(lines)


def _section_company_overview(company) -> str:
    desc = company.description or "No description available."
    return f"""## Company Overview

{desc}

| Attribute | Value |
|-----------|-------|
| **SIC Code** | {company.sic_code or 'N/A'} |
| **Fiscal Year End** | {company.fiscal_year_end or 'N/A'} |
| **Website** | {company.website or 'N/A'} |"""


def _section_financial_performance(incomes, metrics) -> str:
    lines = ["## Financial Performance\n"]

    # Revenue & Income table
    years = [str(inc.fiscal_year) for inc in reversed(incomes)]
    header = "| Metric | " + " | ".join(f"FY{y}" for y in years) + " |"
    sep = "|--------|" + "|".join("--------" for _ in years) + "|"
    lines.append(header)
    lines.append(sep)

    # Revenue
    revs = [inc.revenue for inc in reversed(incomes)]
    lines.append("| **Revenue** | " + " | ".join(f"${_fmt_billions(r)}" for r in revs) + " |")

    # Growth
    if metrics:
        growths = [m.revenue_growth for m in reversed(metrics)]
        lines.append("| Revenue Growth | " + " | ".join(_fmt_growth(g) for g in growths) + " |")

    # Gross Profit
    gps = [inc.gross_profit for inc in reversed(incomes)]
    lines.append("| Gross Profit | " + " | ".join(f"${_fmt_billions(g)}" for g in gps) + " |")

    # Operating Income
    ois = [inc.operating_income for inc in reversed(incomes)]
    lines.append("| Operating Income | " + " | ".join(f"${_fmt_billions(o)}" for o in ois) + " |")

    # Net Income
    nis = [inc.net_income for inc in reversed(incomes)]
    lines.append("| **Net Income** | " + " | ".join(f"${_fmt_billions(n)}" for n in nis) + " |")

    # EPS
    epss = [inc.eps_diluted for inc in reversed(incomes)]
    lines.append("| EPS (Diluted) | " + " | ".join(_fmt_eps(e) for e in epss) + " |")
    lines.append("")

    # Margin trends
    if metrics and len(metrics) >= 2:
        lines.append("### Margin Trends\n")
        m_years = [str(m.fiscal_year) for m in reversed(metrics)]
        m_header = "| Margin | " + " | ".join(f"FY{y}" for y in m_years) + " |"
        m_sep = "|--------|" + "|".join("--------" for _ in m_years) + "|"
        lines.append(m_header)
        lines.append(m_sep)

        for label, attr in [
            ("Gross Margin", "gross_margin"),
            ("Operating Margin", "operating_margin"),
            ("Net Margin", "net_margin"),
            ("FCF Margin", "fcf_margin"),
        ]:
            vals = [getattr(m, attr) for m in reversed(metrics)]
            lines.append(f"| {label} | " + " | ".join(_fmt_margin(v) for v in vals) + " |")

    return "\n".join(lines)


def _section_balance_sheet(balances, metrics) -> str:
    if not balances:
        return ""

    lines = ["## Balance Sheet Highlights\n"]
    bs = balances[0]  # Most recent

    lines.append(f"### FY{bs.fiscal_year} Snapshot\n")
    lines.append("| Item | Value |")
    lines.append("|------|-------|")
    lines.append(f"| Cash & Equivalents | ${_fmt_billions(bs.cash_and_equivalents)} |")
    lines.append(f"| Total Current Assets | ${_fmt_billions(bs.total_current_assets)} |")
    lines.append(f"| Total Assets | ${_fmt_billions(bs.total_assets)} |")
    lines.append(f"| Long-Term Debt | ${_fmt_billions(bs.long_term_debt)} |")
    lines.append(f"| Total Liabilities | ${_fmt_billions(bs.total_liabilities)} |")
    lines.append(f"| Stockholders' Equity | ${_fmt_billions(bs.total_stockholders_equity)} |")

    if metrics:
        m = metrics[0]
        lines.append(f"| Current Ratio | {_fmt_ratio(m.current_ratio)} |")
        lines.append(f"| Debt/Equity | {_fmt_ratio(m.debt_to_equity)} |")

    return "\n".join(lines)


def _section_cash_flow(cash_flows) -> str:
    if not cash_flows:
        return ""

    lines = ["## Cash Flow Analysis\n"]
    years = [str(cf.fiscal_year) for cf in reversed(cash_flows)]
    header = "| Metric | " + " | ".join(f"FY{y}" for y in years) + " |"
    sep = "|--------|" + "|".join("--------" for _ in years) + "|"
    lines.append(header)
    lines.append(sep)

    cfo = [cf.cash_from_operations for cf in reversed(cash_flows)]
    lines.append("| Cash from Operations | " + " | ".join(f"${_fmt_billions(c)}" for c in cfo) + " |")

    capex = [cf.capital_expenditure for cf in reversed(cash_flows)]
    lines.append("| CapEx | " + " | ".join(f"${_fmt_billions(c)}" for c in capex) + " |")

    fcf = [cf.free_cash_flow for cf in reversed(cash_flows)]
    lines.append("| **Free Cash Flow** | " + " | ".join(f"${_fmt_billions(f)}" for f in fcf) + " |")

    sbc = [cf.stock_based_compensation for cf in reversed(cash_flows)]
    lines.append("| Stock-Based Comp | " + " | ".join(f"${_fmt_billions(s)}" for s in sbc) + " |")

    return "\n".join(lines)


def _section_valuation(val: ValuationSummary) -> str:
    lines = ["## Valuation Analysis\n"]

    if val.dcf:
        dcf = val.dcf
        lines.append("### DCF Model\n")
        lines.append("| Parameter | Value |")
        lines.append("|-----------|-------|")
        lines.append(f"| Revenue Growth (Year 1) | {dcf.revenue_growth_rates[0] * 100:.1f}% |")
        lines.append(f"| Operating Margin | {dcf.operating_margin * 100:.1f}% |")
        lines.append(f"| WACC | {dcf.wacc * 100:.1f}% |")
        lines.append(f"| Terminal Growth | {dcf.terminal_growth * 100:.1f}% |")
        lines.append(f"| Tax Rate | {dcf.tax_rate * 100:.1f}% |")
        lines.append(f"| Projection Years | {dcf.projection_years} |")
        lines.append(f"| Enterprise Value | ${dcf.enterprise_value / 1e9:.1f}B |")
        lines.append(f"| Net Debt | ${dcf.net_debt / 1e9:.1f}B |")
        lines.append(f"| Equity Value | ${dcf.equity_value / 1e9:.1f}B |")
        lines.append(f"| Shares Outstanding | {dcf.shares_outstanding / 1e6:.0f}M |")
        lines.append(f"| **Implied Price** | **${dcf.implied_price:.2f}** |")
        lines.append("")

        # Sensitivity table
        if dcf.sensitivity:
            lines.append("### DCF Sensitivity (Implied Price)\n")

            # Build 2D table: WACC (rows) × Terminal Growth (cols)
            waccs = sorted(set(s["wacc"] for s in dcf.sensitivity))
            tgs = sorted(set(s["terminal_growth"] for s in dcf.sensitivity))
            price_map = {(s["wacc"], s["terminal_growth"]): s["price"] for s in dcf.sensitivity}

            header = "| WACC \\ Terminal G | " + " | ".join(f"{tg * 100:.1f}%" for tg in tgs) + " |"
            sep = "|---|" + "|".join("---" for _ in tgs) + "|"
            lines.append(header)
            lines.append(sep)

            for w in waccs:
                row_vals = []
                for tg in tgs:
                    p = price_map.get((w, tg))
                    row_vals.append(f"${p:.2f}" if p else "N/A")
                lines.append(f"| {w * 100:.1f}% | " + " | ".join(row_vals) + " |")
            lines.append("")

    if val.comps and val.comps.peers:
        lines.append("### Comparable Companies\n")
        lines.append("| Ticker | Name | P/E | P/S | EV/EBITDA | Gross Margin | Op Margin |")
        lines.append("|--------|------|-----|-----|-----------|-------------|-----------|")

        # Target row
        t = val.comps.target_metrics
        lines.append(
            f"| **{t['ticker']}** | **{t['name'][:20]}** | "
            f"{_fmt_ratio(t.get('pe_ratio'))} | {_fmt_ratio(t.get('ps_ratio'))} | "
            f"{_fmt_ratio(t.get('ev_to_ebitda'))} | {_fmt_margin(t.get('gross_margin'))} | "
            f"{_fmt_margin(t.get('operating_margin'))} |"
        )

        for p in val.comps.peers:
            lines.append(
                f"| {p['ticker']} | {p['name'][:20]} | "
                f"{_fmt_ratio(p.get('pe_ratio'))} | {_fmt_ratio(p.get('ps_ratio'))} | "
                f"{_fmt_ratio(p.get('ev_to_ebitda'))} | {_fmt_margin(p.get('gross_margin'))} | "
                f"{_fmt_margin(p.get('operating_margin'))} |"
            )
        lines.append("")

        if val.comps.implied_pe:
            lines.append(f"- Implied price from peer P/E: ${val.comps.implied_pe:.2f}")
        if val.comps.implied_ps:
            lines.append(f"- Implied price from peer P/S: ${val.comps.implied_ps:.2f}")

    return "\n".join(lines)


def _section_scenarios(val: ValuationSummary) -> str:
    if not val.scenarios:
        return ""

    lines = ["## Scenario Analysis\n"]
    lines.append("| Scenario | Growth | Op Margin | Terminal G | Implied Price | Upside |")
    lines.append("|----------|--------|-----------|------------|--------------|--------|")

    for name, label, emoji in [("bull", "Bull", "🟢"), ("base", "Base", "🟡"), ("bear", "Bear", "🔴")]:
        s = val.scenarios.scenarios.get(name)
        if not s:
            continue
        upside = f"{s['upside'] * 100:+.1f}%" if s.get("upside") is not None else "N/A"
        lines.append(
            f"| {emoji} **{label}** | {s['revenue_growth'] * 100:.0f}% | "
            f"{s['operating_margin'] * 100:.1f}% | {s['terminal_growth'] * 100:.1f}% | "
            f"${s['implied_price']:.2f} | {upside} |"
        )

    return "\n".join(lines)


def _section_risks_and_catalysts(company, metrics) -> str:
    lines = ["## Investment Thesis & Risks\n"]
    lines.append("### Bull Case (Why Buy)\n")
    lines.append("*Based on financial data patterns:*\n")

    if metrics:
        m = metrics[0]
        if m.revenue_growth and float(m.revenue_growth) > 0.15:
            lines.append(f"- Strong revenue growth ({float(m.revenue_growth) * 100:.1f}% YoY)")
        if m.gross_margin and float(m.gross_margin) > 0.5:
            lines.append(f"- High gross margins ({float(m.gross_margin) * 100:.1f}%) indicating pricing power")
        if m.roe and float(m.roe) > 0.15:
            lines.append(f"- High return on equity ({float(m.roe) * 100:.1f}%)")
        if m.fcf_margin and float(m.fcf_margin) > 0.1:
            lines.append(f"- Strong free cash flow generation ({float(m.fcf_margin) * 100:.1f}% FCF margin)")

    lines.append("\n### Bear Case (Key Risks)\n")
    lines.append("*Areas requiring monitoring:*\n")

    if metrics:
        m = metrics[0]
        if m.revenue_growth and float(m.revenue_growth) < 0:
            lines.append(f"- Revenue declining ({float(m.revenue_growth) * 100:.1f}% YoY)")
        if m.debt_to_equity and float(m.debt_to_equity) > 1.0:
            lines.append(f"- Elevated leverage (D/E: {float(m.debt_to_equity):.1f}x)")
        if m.operating_margin and float(m.operating_margin) < 0.1:
            lines.append(f"- Thin operating margins ({float(m.operating_margin) * 100:.1f}%)")

    lines.append("- Macro & interest rate risk")
    lines.append("- Industry competition and disruption risk")
    lines.append("- Regulatory and geopolitical risk")

    return "\n".join(lines)


def _section_action_plan(val: ValuationSummary, latest_price) -> str:
    lines = ["## What To Do\n"]

    if not val.target_price or not latest_price:
        lines.append("*Insufficient data for specific recommendations.*")
        return "\n".join(lines)

    current = float(latest_price.adjusted_close)
    target = val.target_price

    if val.scenarios and val.scenarios.scenarios:
        bear_price = val.scenarios.scenarios.get("bear", {}).get("implied_price", 0)
        bull_price = val.scenarios.scenarios.get("bull", {}).get("implied_price", 0)
    else:
        bear_price = target * 0.7
        bull_price = target * 1.3

    lines.append(f"**Current Price**: ${current:.2f}")
    lines.append(f"**Fair Value Estimate**: ${target:.2f}")
    lines.append(f"**Downside Protection (Bear Case)**: ${bear_price:.2f}")
    lines.append(f"**Upside Potential (Bull Case)**: ${bull_price:.2f}\n")

    lines.append("### Position Sizing Guide\n")
    lines.append("| Investment Amount | Shares | Exposure |")
    lines.append("|-------------------|--------|----------|")
    for amount in [1000, 5000, 10000, 25000]:
        shares = int(amount / current)
        lines.append(f"| ${amount:,} | {shares} shares | ${shares * current:,.2f} |")

    return "\n".join(lines)


def _section_footer(ticker: str) -> str:
    gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""---

*Generated on {gen_date} | Data source: SEC EDGAR XBRL*
*This report is for informational purposes only and does not constitute financial advice.*
*Always do your own research and consult a qualified financial advisor before investing.*"""


# ──────────────────────────────────────────────
# Save
# ──────────────────────────────────────────────


def _save_report(session, ticker: str, name: str, content: str, params: dict) -> None:
    """Save report to file and database."""
    report_dir = settings.reports_dir / ticker
    report_dir.mkdir(parents=True, exist_ok=True)
    file_path = report_dir / "investment_report.md"
    file_path.write_text(content, encoding="utf-8")
    logger.info(f"Saved investment report to {file_path}")

    existing = (
        session.query(AnalysisReport)
        .filter_by(ticker=ticker, report_type="investment_report")
        .first()
    )

    if existing:
        existing.content_md = content
        existing.title = f"{name} Investment Report"
        existing.parameters = params
        existing.file_path = str(file_path)
        existing.created_at = datetime.utcnow()
    else:
        from src.db.models import AnalysisReport as AR
        report = AR(
            ticker=ticker,
            report_type="investment_report",
            title=f"{name} Investment Report",
            content_md=content,
            parameters=params,
            generated_by="system",
            file_path=str(file_path),
        )
        session.add(report)

    session.flush()
