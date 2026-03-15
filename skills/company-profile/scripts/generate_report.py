"""
Task 3: Generate Company Profile Report
========================================
Assembles a comprehensive markdown company profile from:
  - data/artifacts/{TICKER}/profile/*.json  (created by Tasks 1 & 2)
  - PostgreSQL financial statements          (via ETL pipeline)

Saves the report to:
  - data/artifacts/{TICKER}/profile/company_profile.md  (filesystem)
  - analysis_reports table                              (PostgreSQL)

Usage:
    uv run python skills/company-profile/scripts/generate_report.py NVDA
    uv run python skills/company-profile/scripts/generate_report.py AAPL --price 225.50

Required JSON files in data/artifacts/{TICKER}/profile/:
    company_overview.json       — business description, products, segments, geography
    management_team.json        — executives with bios
    risk_factors.json           — categorized risks from 10-K Item 1A
    competitive_landscape.json  — competitors and moat analysis
    financial_segments.json     — revenue by segment/geography
    investment_thesis.json      — bull case bullets and opportunities
    comps_table.json            — comparable company analysis (from build_comps.py)
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

from src.db.session import get_session
from src.etl.yfinance_client import get_current_price, get_stock_info


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _f(val: Any, default: str = "N/A") -> str:
    """Return str or default if None."""
    return str(val) if val is not None else default


def fmt_b(val: Any, decimals: int = 1) -> str:
    if val is None:
        return "N/A"
    try:
        return f"${float(val):,.{decimals}f}B"
    except (ValueError, TypeError):
        return "N/A"


def fmt_pct(val: Any, decimals: int = 1) -> str:
    """Format change percent with directional arrow."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        arrow = "↑" if v >= 0 else "↓"
        return f"{v:+.{decimals}f}%{arrow}"
    except (ValueError, TypeError):
        return "N/A"


def fmt_pct_plain(val: Any, decimals: int = 1) -> str:
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.{decimals}f}%"
    except (ValueError, TypeError):
        return "N/A"


def fmt_x(val: Any, decimals: int = 1) -> str:
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.{decimals}f}x"
    except (ValueError, TypeError):
        return "N/A"


def fmt_num(val: Any, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return "N/A"


# ── Data loading ───────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict | list:
    """Load a JSON file, return {} if missing or invalid."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def query_financials(ticker: str, session, *, fiscal_year_end: str | None = None) -> list[dict]:
    """Query all annual financial data for a ticker from PostgreSQL.

    Per-share fields (``eps_diluted``) are automatically split-adjusted to the
    current share basis using ``data/artifacts/{TICKER}/profile/stock_splits.json``.
    """
    from src.splits import get_split_adjustor

    rows = session.execute(text("""
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
        ORDER BY i.fiscal_year
    """), {"ticker": ticker}).mappings().all()
    results = [dict(r) for r in rows]

    # Split-adjust per-share metrics to current share basis
    adjust = get_split_adjustor(ticker, fiscal_year_end=fiscal_year_end, db=session)
    for d in results:
        fy = d.get("fiscal_year")
        if fy is not None:
            d["eps_diluted"] = adjust(fy, d.get("eps_diluted"))

    return results


# ── Report sections ────────────────────────────────────────────────────────────

def section_header(ticker: str, name: str, price: float | None, mkt_cap_b: float | None,
                   sector: str, industry: str, exchange: str,
                   fiscal_year_end: str, cik: str, filing_info: str) -> list[str]:
    price_str = f"${price:.2f}" if price else "N/A"
    cap_str = f"${mkt_cap_b:,.0f}B" if mkt_cap_b else "N/A"
    return [
        f"# {name} ({ticker}) — Company Profile",
        "",
        f"**Date:** {date.today().strftime('%B %d, %Y')}  |  "
        f"**Price:** {price_str}  |  **Market Cap:** {cap_str}",
        f"**Sector:** {sector}  |  **Industry:** {industry}  |  **Exchange:** {exchange}",
        f"**Fiscal Year End:** {fiscal_year_end}  |  **CIK:** {cik}  |  **Source:** {filing_info}",
        "",
        "---",
        "",
    ]


def section_business_summary(overview: dict) -> list[str]:
    lines = ["## Business Summary", ""]

    desc = overview.get("description") or overview.get("business_overview", "")
    if desc:
        lines.append(desc)
        lines.append("")

    bo = overview.get("business_overview", "")
    if bo and bo != desc:
        lines.append(bo)
        lines.append("")

    segs = overview.get("segments", [])
    if segs:
        lines.append("**Business Segments:**")
        lines.append("")
        for s in segs:
            rev = s.get("revenue_fy_b") or s.get("revenue_fy2026_b") or s.get("revenue_b")
            growth = s.get("yoy_growth_pct")
            parts = [f"**{s['name']}**: {s.get('description', '')}"]
            if rev is not None:
                parts[0] += f" (FY revenue: {fmt_b(rev)}"
                if growth is not None:
                    parts[0] += f", YoY: {fmt_pct(growth)}"
                parts[0] += ")"
            lines.append(f"- {parts[0]}")
        lines.append("")

    rev_model = overview.get("revenue_model", "")
    if rev_model:
        lines.append(f"**Revenue model:** {rev_model}")
        lines.append("")

    customers = overview.get("customers", "")
    if customers:
        lines.append(f"**Key customers:** {customers}")
        lines.append("")

    geo = overview.get("geographic_revenue", {})
    if geo:
        lines.append("**Geographic revenue (approx.):**")
        for region, pct in geo.items():
            lines.append(f"  - {region}: {pct}")
        lines.append("")

    lines += ["---", ""]
    return lines


def section_management(mgmt: dict) -> list[str]:
    lines = ["## Management Team", ""]
    for exec_info in mgmt.get("executives", []):
        name = exec_info.get("name", "")
        title = exec_info.get("title", "")
        age = exec_info.get("age")
        tenure = exec_info.get("tenure_years")
        ownership = exec_info.get("insider_ownership_pct", "N/A")
        prior = ", ".join(exec_info.get("prior_roles", []))
        accomplishments = exec_info.get("accomplishments", "")

        lines.append(f"### {name} — {title}")
        meta_parts = []
        if age:
            meta_parts.append(f"**Age:** {age}")
        if tenure:
            meta_parts.append(f"**Tenure:** {tenure} years")
        meta_parts.append(f"**Insider Ownership:** {ownership}")
        lines.append("  |  ".join(meta_parts))
        lines.append("")
        if prior:
            lines.append(f"**Prior roles:** {prior}")
            lines.append("")
        if accomplishments:
            lines.append(f"**Key accomplishments:** {accomplishments}")
            lines.append("")

    board = mgmt.get("board", {})
    governance = mgmt.get("governance_notes", "")
    if board or governance:
        board_str = ""
        if board.get("size"):
            board_str = f"**Board:** {board['size']} directors, {board.get('independent_directors', 'N/A')} independent. "
        lines.append(board_str + governance)
        lines.append("")

    lines += ["---", ""]
    return lines


def section_financials(data: list[dict]) -> list[str]:
    if not data:
        return ["## Key Financial Metrics", "", "*No financial data available.*", "", "---", ""]

    yrs = [str(d["fiscal_year"]) for d in data]
    hdr = " | ".join(yrs)
    sep = "|".join(["--------"] * len(yrs))

    def row(label: str, vals: list[str]) -> str:
        return f"| {label} | {' | '.join(vals)} |"

    lines = [f"## Key Financial Metrics (FY{yrs[0]}–FY{yrs[-1]})", "", f"| Metric | {hdr} |", f"|--------|{sep}|"]

    lines.append(row("Revenue ($B)", [fmt_b(d["rev_b"]) for d in data]))
    lines.append(row("Revenue Growth", ["N/A"] + [fmt_pct(d["rev_growth_pct"]) for d in data[1:]]))
    lines.append(row("Gross Profit ($B)", [fmt_b(d["gp_b"]) for d in data]))
    lines.append(row("Operating Income ($B)", [fmt_b(d["oi_b"]) for d in data]))
    lines.append(row("Net Income ($B)", [fmt_b(d["ni_b"]) for d in data]))
    lines.append(row("EPS Diluted", [fmt_num(d["eps_diluted"]) for d in data]))
    lines.append(row("Free Cash Flow ($B)", [fmt_b(d["fcf_b"]) for d in data]))
    if any(d.get("rd_b") for d in data):
        lines.append(row("R&D Expense ($B)", [fmt_b(d.get("rd_b")) for d in data]))

    lines += ["", "---", ""]
    return lines


def section_margins(data: list[dict]) -> list[str]:
    if not data:
        return []
    yrs = [str(d["fiscal_year"]) for d in data]
    hdr = " | ".join(yrs)
    sep = "|".join(["--------"] * len(yrs))

    def row(label: str, vals: list[str]) -> str:
        return f"| {label} | {' | '.join(vals)} |"

    latest = data[-1]
    prev = data[-2] if len(data) >= 2 else None

    lines = [
        "## Margin Analysis", "",
        f"| Margin | {hdr} |", f"|--------|{sep}|",
    ]
    lines.append(row("Gross Margin", [fmt_pct_plain(d["gm_pct"]) for d in data]))
    lines.append(row("Operating Margin", [fmt_pct_plain(d["om_pct"]) for d in data]))
    lines.append(row("Net Margin", [fmt_pct_plain(d["nm_pct"]) for d in data]))
    lines.append(row("FCF Margin", [fmt_pct_plain(d["fcf_margin_pct"]) for d in data]))
    lines.append("")

    # Trend commentary
    if prev and latest:
        gm_trend = (float(latest["gm_pct"] or 0) - float(prev["gm_pct"] or 0))
        om_trend = (float(latest["om_pct"] or 0) - float(prev["om_pct"] or 0))
        trend_word_gm = "expanded" if gm_trend >= 0 else "compressed"
        trend_word_om = "expanded" if om_trend >= 0 else "compressed"
        lines.append(
            f"**FY{latest['fiscal_year']} margins:** Gross margin {fmt_pct_plain(latest['gm_pct'])} "
            f"({trend_word_gm} {abs(gm_trend):.1f}pp YoY). "
            f"Operating margin {fmt_pct_plain(latest['om_pct'])} "
            f"({trend_word_om} {abs(om_trend):.1f}pp YoY)."
        )
        lines.append("")

    lines += ["---", ""]
    return lines


def section_balance_sheet(data: list[dict]) -> list[str]:
    if not data:
        return []
    latest = data[-1]
    prev = data[-2] if len(data) >= 2 else None
    fy = latest["fiscal_year"]
    fy_prev = prev["fiscal_year"] if prev else fy - 1

    def bs_row(label: str, key: str) -> str:
        v = latest.get(key)
        p = (prev or {}).get(key) if prev else None
        chg = (float(v) - float(p)) if (v is not None and p is not None) else None
        return f"| {label} | {fmt_b(v)} | {fmt_b(p)} | {fmt_b(chg) if chg is not None else 'N/A'} |"

    lines = [
        f"## Balance Sheet Snapshot (FY{fy} vs FY{fy_prev})", "",
        f"| Item | FY{fy} | FY{fy_prev} | Change |",
        "|------|--------|--------|--------|",
    ]
    lines.append(bs_row("Cash & Equivalents", "cash_b"))
    lines.append(bs_row("Short-term Investments", "sti_b"))
    lines.append(bs_row("Accounts Receivable", "ar_b"))
    lines.append(bs_row("Inventory", "inv_b"))
    lines.append(bs_row("Total Current Assets", "cur_assets_b"))
    lines.append(bs_row("Total Assets", "assets_b"))
    lines.append(bs_row("Short-term Debt", "std_b"))
    lines.append(bs_row("Long-term Debt", "ltd_b"))
    lines.append(bs_row("Total Current Liabilities", "cur_liab_b"))
    lines.append(bs_row("Total Equity", "equity_b"))
    lines.append("")

    cash = (latest.get("cash_b") or 0)
    sti = (latest.get("sti_b") or 0)
    ltd = (latest.get("ltd_b") or 0)
    std = (latest.get("std_b") or 0)
    try:
        net_cash = float(cash) + float(sti) - float(ltd) - float(std)
        net_label = "net cash" if net_cash >= 0 else "net debt"
        lines.append(f"**{net_label.capitalize()}:** ${abs(net_cash):.1f}B  |  "
                     f"**Current Ratio:** {fmt_x(latest.get('current_ratio'))}  |  "
                     f"**Debt/Equity:** {fmt_x(latest.get('debt_to_equity'))}")
    except (TypeError, ValueError):
        pass
    lines.append("")
    lines += ["---", ""]
    return lines


def section_returns(data: list[dict]) -> list[str]:
    if not data:
        return []
    yrs = [str(d["fiscal_year"]) for d in data]
    hdr = " | ".join(yrs)
    sep = "|".join(["--------"] * len(yrs))

    def row(label: str, vals: list[str]) -> str:
        return f"| {label} | {' | '.join(vals)} |"

    lines = ["## Returns & Efficiency", "", f"| Metric | {hdr} |", f"|--------|{sep}|"]
    lines.append(row("ROE", [fmt_pct_plain(d.get("roe_pct")) for d in data]))
    lines.append(row("ROA", [fmt_pct_plain(d.get("roa_pct")) for d in data]))
    lines.append(row("ROIC", [fmt_pct_plain(d.get("roic_pct")) for d in data]))
    lines += ["", "---", ""]
    return lines


def section_valuation(ticker: str, mkt_cap_b: float | None, price: float | None,
                      data: list[dict], info: dict) -> list[str]:
    if not data or not mkt_cap_b:
        return []
    latest = data[-1]
    ni = latest.get("ni_b")
    rev = latest.get("rev_b")
    fcf = latest.get("fcf_b")
    eq = latest.get("equity_b")

    pe_ttm = (mkt_cap_b / float(ni)) if ni and float(ni) > 0 else None
    ps_ttm = (mkt_cap_b / float(rev)) if rev and float(rev) > 0 else None
    pb = (mkt_cap_b / float(eq)) if eq and float(eq) > 0 else None
    fcf_yield = (float(fcf) / mkt_cap_b * 100) if fcf and mkt_cap_b else None
    pe_fwd = info.get("pe_forward")
    ev_ebitda = info.get("ev_to_ebitda")

    price_str = f"${price:.2f}" if price else "N/A"
    cap_str = f"${mkt_cap_b:,.0f}B"

    lines = [
        "## Valuation", "",
        f"*As of {date.today().strftime('%B %d, %Y')}  |  Price: {price_str}  |  Market Cap: {cap_str}*",
        "",
        "| Metric | Value | Notes |",
        "|--------|-------|-------|",
        f"| Price | {price_str} | Current close |",
        f"| Market Cap | {cap_str} | Fully diluted |",
        f"| P/E (Forward) | {fmt_x(pe_fwd)} | FY+1E consensus |",
        f"| P/E (TTM) | {fmt_x(pe_ttm)} | LTM net income |",
        f"| EV/EBITDA | {fmt_x(ev_ebitda)} | TTM |",
        f"| P/S (TTM) | {fmt_x(ps_ttm)} | LTM revenue |",
        f"| P/B | {fmt_x(pb)} | Latest book value |",
        f"| FCF Yield | {fmt_pct_plain(fcf_yield)} | LTM FCF / Market Cap |",
        "",
        "---",
        "",
    ]
    return lines


def section_comps(ticker: str, comps_data: dict) -> list[str]:
    peers = comps_data.get("peers", [])
    summary = comps_data.get("peer_summary", {})
    if not peers:
        return []

    lines = [
        "## Comparable Company Analysis", "",
        f"*Source: Yahoo Finance — {comps_data.get('generated_date', 'N/A')}*",
        "",
        "| Company | Ticker | Mkt Cap ($B) | Rev LTM ($B) | Rev Growth | Gross Margin | Op Margin | P/E Fwd | EV/EBITDA | P/S |",
        "|---------|--------|-------------|-------------|-----------|-------------|---------|---------|-----------|-----|",
    ]

    for p in peers:
        flag = " ⭐" if p["ticker"] == ticker else ""
        rg = fmt_pct(p.get("rev_growth_pct")) if p.get("rev_growth_pct") is not None else "N/A"
        lines.append(
            f"| {p['name']}{flag} | {p['ticker']} | "
            f"${p['market_cap_b']:.0f}B | "
            f"{fmt_b(p.get('revenue_ltm_b'))} | {rg} | "
            f"{fmt_pct_plain(p.get('gross_margin_pct'))} | "
            f"{fmt_pct_plain(p.get('operating_margin_pct'))} | "
            f"{fmt_x(p.get('pe_forward'))} | "
            f"{fmt_x(p.get('ev_ebitda'))} | "
            f"{fmt_x(p.get('ps_ratio'))} |"
        )

    # Peer summary row
    def s(key, sub="median"):
        v = summary.get(key)
        if isinstance(v, dict):
            return v.get(sub)
        return v

    lines.append(
        f"| **Peer Median** | — | — | — | — | "
        f"**{fmt_pct_plain(s('gross_margin_pct'))}** | "
        f"**{fmt_pct_plain(s('operating_margin_pct'))}** | "
        f"**{fmt_x(s('pe_forward'))}** | "
        f"**{fmt_x(s('ev_ebitda'))}** | "
        f"**{fmt_x(s('ps_ratio'))}** |"
    )

    lines += ["", "---", ""]
    return lines


def section_competitive(competitive: dict) -> list[str]:
    if not competitive:
        return []
    lines = [
        "## Competitive Landscape", "",
    ]
    moat = competitive.get("moat", "")
    if moat:
        lines.append(f"**Competitive Moat:** {moat}")
        lines.append("")
    positioning = competitive.get("competitive_positioning", "")
    if positioning:
        lines.append(f"**Market Position:** {positioning}")
        lines.append("")

    competitors = competitive.get("competitors", [])
    if competitors:
        lines.append("### Key Competitors")
        lines.append("")
        for comp in competitors:
            mkt = f"${comp.get('market_cap_b', 0):.0f}B" if comp.get("market_cap_b") else "N/A"
            lines.append(f"**{comp['name']} ({comp.get('ticker', 'N/A')})** — Market Cap: {mkt}")
            if comp.get("products_competing"):
                lines.append(f"- Products: {comp['products_competing']}")
            if comp.get("competitive_advantage_vs_subject") or comp.get("competitive_advantage_vs_nvda"):
                adv = comp.get("competitive_advantage_vs_subject") or comp.get("competitive_advantage_vs_nvda")
                lines.append(f"- Their advantage: {adv}")
            share = comp.get("market_share_ai_accelerators") or comp.get("market_share")
            if share:
                lines.append(f"- Market share: {share}")
            lines.append("")

    lines += ["---", ""]
    return lines


def section_investment_thesis(thesis: dict, ticker: str) -> list[str]:
    bull = thesis.get("bull_case", [])
    if not bull:
        return []
    lines = ["## Investment Thesis — Bull Case", ""]
    for i, item in enumerate(bull, 1):
        title = item.get("title", f"Point {i}")
        desc = item.get("description", "")
        lines.append(f"{i}. **{title}**: {desc}")
        lines.append("")
    lines += ["---", ""]
    return lines


def section_risks(risks_data: dict) -> list[str]:
    risks = risks_data.get("risks", [])
    if not risks:
        return []
    lines = [
        "## Key Risks", "",
        f"*Sourced from 10-K {risks_data.get('source', 'Item 1A')}*",
        "",
    ]
    for risk in risks:
        cat = risk.get("category", "")
        title = risk.get("title", "")
        desc = risk.get("description", "")
        lines.append(f"**[{cat}] {title}**")
        lines.append(desc)
        lines.append("")
    lines += ["---", ""]
    return lines


def section_opportunities(thesis: dict) -> list[str]:
    opps = thesis.get("opportunities", [])
    if not opps:
        return []
    lines = ["## Opportunities & Catalysts", ""]
    for i, opp in enumerate(opps, 1):
        title = opp.get("title", f"Opportunity {i}")
        desc = opp.get("description", "")
        lines.append(f"{i}. **{title}**: {desc}")
        lines.append("")
    lines += ["---", ""]
    return lines


def section_appendix(ticker: str, processed_dir: Path) -> list[str]:
    files = [p.name for p in processed_dir.iterdir()] if processed_dir.exists() else []
    return [
        "## Appendix: Data Sources", "",
        "| Section | Source |",
        "|---------|--------|",
        "| Financial Statements | MCP (PostgreSQL) via ETL pipeline |",
        "| 10-K Sections | SEC EDGAR HTML filing, parsed by section_extractor.py |",
        "| Management / Risks / Business | 10-K Item 1, 1A, 7, 10 (AI-parsed via MCP) |",
        "| Market Data, Valuation | Alpha Vantage / Yahoo Finance |",
        "| Comparable Companies | Yahoo Finance, build_comps.py |",
        "",
        f"*Processed files: {', '.join(sorted(files))}*",
        "",
        f"*Report generated by Claude (AI) on {date.today().strftime('%B %d, %Y')}.*",
        "",
    ]


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Task 3: Generate company profile report")
    parser.add_argument("ticker", help="Stock ticker, e.g. NVDA")
    parser.add_argument("--price", type=float, default=None, help="Override current price")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    processed_dir = Path(f"data/artifacts/{ticker}/profile")
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ── Load all processed JSON files ──────────────────────────────────────────
    overview     = load_json(processed_dir / "company_overview.json")
    mgmt         = load_json(processed_dir / "management_team.json")
    risks_data   = load_json(processed_dir / "risk_factors.json")
    competitive  = load_json(processed_dir / "competitive_landscape.json")
    segments     = load_json(processed_dir / "financial_segments.json")
    thesis       = load_json(processed_dir / "investment_thesis.json")
    comps_data   = load_json(processed_dir / "comps_table.json")

    # ── Fetch market data ──────────────────────────────────────────────────────
    price = args.price or get_current_price(ticker)
    info = get_stock_info(ticker)
    mkt_cap = (info.get("market_cap") or 0) / 1e9 or None
    sector = info.get("sector", "N/A")
    industry = info.get("industry", "N/A")
    exchange = info.get("exchange", "N/A")
    company_name = overview.get("company_name") or info.get("name") or ticker

    # ── Company metadata ───────────────────────────────────────────────────────
    # Try to get from overview, fall back to info
    cik = overview.get("cik", "N/A")
    filing_info = overview.get("source") or f"SEC EDGAR 10-K (latest)"
    fiscal_year_end = overview.get("fiscal_year_end", "December")

    # ── Query PostgreSQL financial data ────────────────────────────────────────
    session = get_session()

    # Resolve fiscal-year-end code for split adjustment (e.g. "0131" for Jan 31)
    fye_code: str | None = None
    try:
        row = session.execute(
            text("SELECT fiscal_year_end FROM companies WHERE ticker = :t"),
            {"t": ticker},
        ).fetchone()
        if row:
            fye_code = row[0]
    except Exception:
        pass

    try:
        fin_data = query_financials(ticker, session, fiscal_year_end=fye_code)
    except Exception as e:
        print(f"Warning: DB query failed: {e}")
        fin_data = []

    if not fin_data:
        print(f"Warning: No financial data in DB for {ticker}. Run ETL first: uv run python -m src.etl.pipeline ingest {ticker} --years 5")

    # ── Assemble report ────────────────────────────────────────────────────────
    all_sections: list[str] = []
    all_sections += section_header(
        ticker, company_name, price, mkt_cap, sector, industry,
        exchange, fiscal_year_end, cik, filing_info
    )
    all_sections += section_business_summary(overview or segments)
    if mgmt:
        all_sections += section_management(mgmt)
    if fin_data:
        all_sections += section_financials(fin_data)
        all_sections += section_margins(fin_data)
        all_sections += section_balance_sheet(fin_data)
        all_sections += section_returns(fin_data)
    all_sections += section_valuation(ticker, mkt_cap, price, fin_data, info)
    if comps_data:
        all_sections += section_comps(ticker, comps_data)
    if competitive:
        all_sections += section_competitive(competitive)
    if thesis.get("bull_case"):
        all_sections += section_investment_thesis(thesis, ticker)
    if risks_data:
        all_sections += section_risks(risks_data)
    if thesis.get("opportunities"):
        all_sections += section_opportunities(thesis)
    all_sections += section_appendix(ticker, processed_dir)

    report_md = "\n".join(all_sections)

    # ── Save to filesystem ──────────────────────────────────────────────────────
    out_path = processed_dir / "company_profile.md"
    out_path.write_text(report_md)
    print(f"Saved: {out_path}  ({len(report_md):,} chars, {len(all_sections)} lines)")

    # ── Upsert to PostgreSQL ────────────────────────────────────────────────────
    try:
        # Delete existing first (no unique constraint on analysis_reports by default)
        session.execute(text(
            "DELETE FROM analysis_reports WHERE ticker=:t AND report_type='company_profile'"
        ), {"t": ticker})
        session.execute(text("""
            INSERT INTO analysis_reports (ticker, report_type, title, content_md, generated_by, file_path)
            VALUES (:ticker, :rtype, :title, :content, 'claude', :path)
        """), {
            "ticker": ticker,
            "rtype": "company_profile",
            "title": f"{company_name} Company Profile",
            "content": report_md,
            "path": str(out_path.resolve()),
        })
        session.commit()
        print(f"Saved to analysis_reports table (ticker={ticker}, report_type=company_profile)")
    except Exception as e:
        print(f"DB save warning: {e}")
        session.rollback()
    finally:
        session.close()

    print(f"\n✓ Report complete: data/artifacts/{ticker}/profile/company_profile.md")
    print(f"  View in Streamlit: http://localhost:8501")


if __name__ == "__main__":
    main()
