"""Investment report generator.

Produces a comprehensive markdown investment report by combining:
  - Artifact JSON files (``data/artifacts/<ticker>/``)
  - Database financials (via :func:`~src.analysis.company_profile.get_profile_data`)
  - DCF valuation (via :func:`~src.analysis.valuation.valuation_summary`)

Public API
----------
.. code-block:: python

    from pfs.services.investment_report import generate_investment_report

    md = generate_investment_report("NVDA", revenue_growth=0.20, wacc=0.10, save=True)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | list | None:
    """Load JSON from *path*, returning ``None`` on any error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fmt_bn(value: float | None, decimals: int = 1) -> str:
    """Format a raw dollar value as $X.XB, or '—' if missing."""
    if value is None:
        return "—"
    return f"${value / 1e9:,.{decimals}f}B"


def _fmt_pct(value: float | None, decimals: int = 1, signed: bool = False) -> str:
    """Format a decimal ratio as a percentage string."""
    if value is None:
        return "—"
    fmt = f"{value * 100:+.{decimals}f}%" if signed else f"{value * 100:.{decimals}f}%"
    return fmt


def _fmt_mult(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}x"


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def generate_investment_report(
    ticker: str,
    *,
    revenue_growth: float | None = None,
    wacc: float | None = None,
    save: bool = True,
) -> str:
    """Generate a comprehensive investment report for *ticker*.

    Args:
        ticker:         Company ticker, e.g. ``"NVDA"``.
        revenue_growth: Optional override for Year-1 revenue growth (decimal).
        wacc:           Optional override for WACC (decimal).
        save:           If ``True``, write the report to
                        ``data/reports/<ticker>/investment_report.md``.

    Returns:
        Full markdown report as a string.
    """
    ticker = ticker.upper()
    processed = Path("data/artifacts") / ticker

    # ── Load JSON sources ───────────────────────────────────────────────────
    overview: dict = _load_json(processed / "company_overview.json") or {}
    thesis: dict = _load_json(processed / "investment_thesis.json") or {}
    competitive: dict = _load_json(processed / "competitive_landscape.json") or {}
    comps_data: dict = _load_json(processed / "comps_table.json") or {}
    risk_data: dict = _load_json(processed / "risk_factors.json") or {}
    segments_data: dict = _load_json(processed / "financial_segments.json") or {}
    mgmt_data: dict = _load_json(processed / "management_team.json") or {}

    # ── DB financials ───────────────────────────────────────────────────────
    from pfs.services.analysis import get_profile_data

    profile = get_profile_data(ticker, years=5)
    company_db: dict = profile.get("company") or {}
    incomes: list[dict] = profile.get("income_statements") or []
    balances: list[dict] = profile.get("balance_sheets") or []
    cash_flows: list[dict] = profile.get("cash_flows") or []
    metrics: list[dict] = profile.get("metrics") or []
    latest_price_db: dict = profile.get("latest_price") or {}

    latest_income: dict = incomes[-1] if incomes else {}
    latest_balance: dict = balances[-1] if balances else {}
    latest_cf: dict = cash_flows[-1] if cash_flows else {}
    latest_metrics: dict = metrics[-1] if metrics else {}

    # ── Valuation ───────────────────────────────────────────────────────────
    from pfs.services.valuation import valuation_summary

    val = valuation_summary(ticker, revenue_growth=revenue_growth, wacc=wacc)

    # ── Derived values ──────────────────────────────────────────────────────
    company_name = (
        overview.get("company_name")
        or company_db.get("name")
        or ticker
    )
    current_price = (
        latest_price_db.get("close")
        or latest_price_db.get("price")
    )
    today = date.today().isoformat()

    lines: list[str] = []

    # ════════════════════════════════════════════════════════════════════════
    # HEADER
    # ════════════════════════════════════════════════════════════════════════
    recommendation = val.recommendation or "HOLD"
    target_price_str = _fmt_price(val.target_price)
    upside_str = _fmt_pct(val.upside_pct, signed=True) if val.upside_pct is not None else "—"

    lines += [
        f"# {company_name} ({ticker}) — Investment Report",
        f"*Generated: {today}*",
        "",
        f"**Rating:** {recommendation} &nbsp;|&nbsp; "
        f"**Target Price:** {target_price_str} &nbsp;|&nbsp; "
        f"**Current Price:** {_fmt_price(current_price)} &nbsp;|&nbsp; "
        f"**Upside:** {upside_str}",
        "",
        "---",
        "",
    ]

    # ════════════════════════════════════════════════════════════════════════
    # 1. EXECUTIVE SUMMARY
    # ════════════════════════════════════════════════════════════════════════
    lines.append("## 1. Executive Summary")

    description = (
        overview.get("description")
        or overview.get("business_overview")
        or company_db.get("description")
        or ""
    )
    if description:
        lines += [description, ""]

    # Bull case headline items
    bull_items: list[dict] = thesis.get("bull_case") or []
    if bull_items:
        lines.append("**Key Investment Highlights:**")
        for item in bull_items[:3]:
            title = item.get("title") or item.get("point") or ""
            desc = item.get("description") or item.get("detail") or ""
            if title:
                lines.append(f"- **{title}**" + (f": {desc}" if desc else ""))
        lines.append("")

    # ════════════════════════════════════════════════════════════════════════
    # 2. COMPANY OVERVIEW
    # ════════════════════════════════════════════════════════════════════════
    lines.append("## 2. Company Overview")

    sector = overview.get("sector") or company_db.get("sector") or "—"
    industry = overview.get("industry") or company_db.get("industry") or "—"
    headquarters = overview.get("headquarters") or company_db.get("headquarters") or "—"
    founded = overview.get("founded") or overview.get("year_founded") or "—"
    employees = overview.get("employees") or overview.get("num_employees")

    lines += [
        f"| Field | Value |",
        f"| --- | --- |",
        f"| Sector | {sector} |",
        f"| Industry | {industry} |",
        f"| Headquarters | {headquarters} |",
        f"| Founded | {founded} |",
    ]
    if employees:
        lines.append(f"| Employees | {employees:,} |" if isinstance(employees, int) else f"| Employees | {employees} |")
    lines.append("")

    # Management team
    exec_team: list[dict] = mgmt_data.get("executives") or mgmt_data.get("management") or []
    if exec_team:
        lines.append("**Key Executives:**")
        lines.append("| Name | Title |")
        lines.append("| --- | --- |")
        for exec_ in exec_team[:6]:
            name = exec_.get("name") or exec_.get("person") or ""
            title = exec_.get("title") or exec_.get("role") or ""
            if name:
                lines.append(f"| {name} | {title} |")
        lines.append("")

    # Business segments
    segs: list[dict] = segments_data.get("segments") or []
    if segs:
        lines.append("**Business Segments:**")
        lines.append("| Segment | Revenue | % of Total |")
        lines.append("| --- | --- | --- |")
        for seg in segs:
            seg_name = seg.get("name") or seg.get("segment") or ""
            seg_rev = seg.get("revenue")
            seg_pct = seg.get("percentage") or seg.get("pct") or seg.get("share")
            rev_str = _fmt_bn(seg_rev) if isinstance(seg_rev, (int, float)) else (seg_rev or "—")
            pct_str = f"{seg_pct:.1f}%" if isinstance(seg_pct, (int, float)) else (seg_pct or "—")
            lines.append(f"| {seg_name} | {rev_str} | {pct_str} |")
        lines.append("")

    # ════════════════════════════════════════════════════════════════════════
    # 3. FINANCIAL ANALYSIS
    # ════════════════════════════════════════════════════════════════════════
    lines.append("## 3. Financial Analysis")

    if incomes:
        lines.append("### Income Statement Summary")
        lines.append("| Year | Revenue | Gross Profit | Operating Income | Net Income |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in incomes:
            fy = row.get("fiscal_year", "—")
            rev = _fmt_bn(row.get("revenue"))
            gp = _fmt_bn(row.get("gross_profit"))
            oi = _fmt_bn(row.get("operating_income"))
            ni = _fmt_bn(row.get("net_income"))
            lines.append(f"| {fy} | {rev} | {gp} | {oi} | {ni} |")
        lines.append("")

    if metrics:
        lines.append("### Margin & Growth Trends")
        lines.append("| Year | Rev Growth | Gross Margin | Op Margin | Net Margin |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in metrics:
            fy = row.get("fiscal_year", "—")
            rg = _fmt_pct(row.get("revenue_growth"), signed=True)
            gm = _fmt_pct(row.get("gross_margin"))
            om = _fmt_pct(row.get("operating_margin"))
            nm = _fmt_pct(row.get("net_margin"))
            lines.append(f"| {fy} | {rg} | {gm} | {om} | {nm} |")
        lines.append("")

    if balances:
        lines += [
            "### Balance Sheet Highlights (Latest Year)",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Cash & Equivalents | {_fmt_bn(latest_balance.get('cash_and_equivalents'))} |",
            f"| Total Assets | {_fmt_bn(latest_balance.get('total_assets'))} |",
            f"| Total Debt | {_fmt_bn(latest_balance.get('total_debt'))} |",
            f"| Total Equity | {_fmt_bn(latest_balance.get('total_equity'))} |",
            "",
        ]

    if cash_flows:
        lines += [
            "### Cash Flow Highlights (Latest Year)",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Operating Cash Flow | {_fmt_bn(latest_cf.get('operating_cash_flow'))} |",
            f"| Capital Expenditures | {_fmt_bn(latest_cf.get('capex'))} |",
            f"| Free Cash Flow | {_fmt_bn(latest_cf.get('free_cash_flow'))} |",
            "",
        ]

    # ════════════════════════════════════════════════════════════════════════
    # 4. VALUATION
    # ════════════════════════════════════════════════════════════════════════
    lines.append("## 4. Valuation")

    if val.dcf:
        dcf = val.dcf
        lines += [
            "### DCF Analysis",
            "| Parameter | Value |",
            "| --- | --- |",
            f"| Implied Price (per share) | {_fmt_price(dcf.implied_price)} |",
            f"| Current Price | {_fmt_price(current_price)} |",
            f"| Upside / (Downside) | {upside_str} |",
            f"| Enterprise Value | {_fmt_bn(dcf.enterprise_value)} |",
            f"| Equity Value | {_fmt_bn(dcf.equity_value)} |",
            f"| WACC | {_fmt_pct(dcf.wacc)} |",
            f"| Terminal Growth | {_fmt_pct(dcf.terminal_growth)} |",
            "",
        ]

        # sensitivity is list[dict] with keys "wacc", "terminal_growth", "price"
        if dcf.sensitivity:
            lines.append("### Sensitivity Analysis (Implied Price per Share)")
            # Collect unique sorted WACC / TG values
            wacc_vals = sorted({s["wacc"] for s in dcf.sensitivity})
            tg_vals = sorted({s["terminal_growth"] for s in dcf.sensitivity})
            price_map = {(s["wacc"], s["terminal_growth"]): s["price"] for s in dcf.sensitivity}

            if wacc_vals and tg_vals:
                header = "| WACC \\ TG | " + " | ".join(f"{g*100:.1f}%" for g in tg_vals) + " |"
                sep = "| --- |" + " --- |" * len(tg_vals)
                lines += [header, sep]
                for w in wacc_vals:
                    row_vals = " | ".join(
                        _fmt_price(price_map.get((w, g))) for g in tg_vals
                    )
                    lines.append(f"| {w*100:.1f}% | {row_vals} |")
                lines.append("")

    if val.scenarios:
        lines.append("### Scenario Analysis")
        lines.append("| Scenario | Implied Price | Upside |")
        lines.append("| --- | --- | --- |")
        # ScenariosResult.scenarios is dict[str, dict[str, Any]]
        scen_dict = val.scenarios.scenarios if hasattr(val.scenarios, "scenarios") else {}
        for scenario_name, scen_info in scen_dict.items():
            if scen_info is None:
                continue
            sv = scen_info.get("implied_price") or scen_info.get("price")
            su = (sv / current_price - 1) if (sv and current_price) else None
            lines.append(
                f"| {scenario_name.title()} | {_fmt_price(sv)} | {_fmt_pct(su, signed=True)} |"
            )
        lines.append("")

    # Comps table
    peers: list[dict] = comps_data.get("peers") or []
    if not peers and val.comps:
        peers = val.comps.peers or []
    if peers:
        lines.append("### Comparable Companies")
        lines.append("| Ticker | Market Cap | Rev Growth | Gross Margin | Fwd P/E | EV/EBITDA |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for p in peers:
            t = p.get("ticker") or p.get("symbol") or ""
            mc_raw = p.get("market_cap_b") or (p.get("market_cap") / 1e9 if p.get("market_cap") else None)
            mc = f"${mc_raw:.0f}B" if mc_raw is not None else "—"
            rg_raw = p.get("rev_growth_pct") or (p.get("revenue_growth") * 100 if p.get("revenue_growth") else None)
            rg = f"{rg_raw:.1f}%" if rg_raw is not None else "—"
            gm_raw = p.get("gross_margin_pct") or (p.get("gross_margin") * 100 if p.get("gross_margin") else None)
            gm = f"{gm_raw:.1f}%" if gm_raw is not None else "—"
            pe = _fmt_mult(p.get("pe_forward") or p.get("forward_pe"))
            ev = _fmt_mult(p.get("ev_ebitda") or p.get("ev_to_ebitda"))
            lines.append(f"| {t} | {mc} | {rg} | {gm} | {pe} | {ev} |")
        lines.append("")

    # ════════════════════════════════════════════════════════════════════════
    # 5. INVESTMENT THESIS
    # ════════════════════════════════════════════════════════════════════════
    if thesis:
        lines.append("## 5. Investment Thesis")

        for case_key, heading in [("bull_case", "### Bull Case"), ("bear_case", "### Bear Case")]:
            items: list[dict] = thesis.get(case_key) or []
            if items:
                lines.append(heading)
                for item in items:
                    title = item.get("title") or item.get("point") or ""
                    desc = item.get("description") or item.get("detail") or ""
                    if title:
                        lines.append(f"**{title}**")
                        if desc:
                            lines.append(desc)
                        lines.append("")

        summary = thesis.get("summary") or thesis.get("thesis_summary") or ""
        if summary:
            lines += ["### Summary", summary, ""]

    # ════════════════════════════════════════════════════════════════════════
    # 6. COMPETITIVE LANDSCAPE
    # ════════════════════════════════════════════════════════════════════════
    if competitive:
        lines.append("## 6. Competitive Landscape")

        market_position = (
            competitive.get("market_position")
            or competitive.get("competitive_position")
            or ""
        )
        if market_position:
            lines += [market_position, ""]

        moat = competitive.get("moat") or competitive.get("competitive_advantages") or []
        if isinstance(moat, list) and moat:
            lines.append("**Competitive Advantages (Moat):**")
            for item in moat:
                if isinstance(item, str):
                    lines.append(f"- {item}")
                elif isinstance(item, dict):
                    t = item.get("title") or item.get("advantage") or ""
                    d = item.get("description") or item.get("detail") or ""
                    lines.append(f"- **{t}**" + (f": {d}" if d else "") if t else f"- {d}")
            lines.append("")
        elif isinstance(moat, str) and moat:
            lines += [moat, ""]

        competitors: list[dict] = competitive.get("key_competitors") or competitive.get("competitors") or []
        if competitors:
            lines.append("**Key Competitors:**")
            lines.append("| Company | Ticker | Strengths |")
            lines.append("| --- | --- | --- |")
            for c in competitors[:6]:
                cname = c.get("name") or c.get("company") or ""
                ctick = c.get("ticker") or c.get("symbol") or "—"
                cstr = c.get("strengths") or c.get("description") or c.get("detail") or "—"
                if isinstance(cstr, list):
                    cstr = "; ".join(cstr)
                lines.append(f"| {cname} | {ctick} | {cstr} |")
            lines.append("")

    # ════════════════════════════════════════════════════════════════════════
    # 7. RISK FACTORS
    # ════════════════════════════════════════════════════════════════════════
    if risk_data:
        lines.append("## 7. Risk Factors")

        risks: list[dict] = risk_data.get("risks") or risk_data.get("risk_factors") or []
        if isinstance(risk_data, list):
            risks = risk_data

        for risk in risks:
            if isinstance(risk, str):
                lines.append(f"- {risk}")
                continue
            title = risk.get("title") or risk.get("risk") or risk.get("name") or ""
            desc = risk.get("description") or risk.get("detail") or risk.get("summary") or ""
            severity = risk.get("severity") or risk.get("level") or ""
            sev_str = f" *(Severity: {severity})*" if severity else ""
            if title:
                lines.append(f"**{title}**{sev_str}")
                if desc:
                    lines.append(desc)
                lines.append("")
        lines.append("")

    # ════════════════════════════════════════════════════════════════════════
    # FOOTER
    # ════════════════════════════════════════════════════════════════════════
    lines += [
        "---",
        f"*Report generated {today}. Data sourced from SEC EDGAR XBRL filings and Yahoo Finance. "
        "This report is for informational purposes only and does not constitute investment advice.*",
    ]

    report_md = "\n".join(lines)

    # ── Optionally save ─────────────────────────────────────────────────────
    if save:
        out_dir = Path("data/reports") / ticker
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "investment_report.md"
        out_path.write_text(report_md, encoding="utf-8")

    return report_md
