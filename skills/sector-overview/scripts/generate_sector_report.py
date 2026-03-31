#!/usr/bin/env python3
"""Generate a sector overview markdown report from collected sector data.

Reads ``sector_data.json`` and produces a comprehensive ``sector_overview.md``
with competitive landscape tables, valuation context, and investment themes.

Usage::

    uv run python skills/sector-overview/scripts/generate_sector_report.py --sector Technology
    uv run python skills/sector-overview/scripts/generate_sector_report.py --sector Technology --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import httpx

from artifact_io import ArtifactIO, slugify

API_URL = os.getenv("PFS_API_URL", "http://localhost:8000")


# ── Formatting helpers ───────────────────────────────────────────────────────


def fmt_pct(val: float | None, decimal: int = 1) -> str:
    """Format a decimal ratio as a percentage string."""
    if val is None:
        return "—"
    return f"{val * 100:.{decimal}f}%"


def fmt_number(val: float | None, decimal: int = 1) -> str:
    """Format a number with specified decimals."""
    if val is None:
        return "—"
    return f"{val:.{decimal}f}"


def fmt_billions(val: float | None) -> str:
    """Format large numbers in billions."""
    if val is None:
        return "—"
    if abs(val) >= 1e12:
        return f"${val / 1e12:.1f}T"
    if abs(val) >= 1e9:
        return f"${val / 1e9:.1f}B"
    if abs(val) >= 1e6:
        return f"${val / 1e6:.0f}M"
    return f"${val:,.0f}"


def fmt_ratio(val: float | None) -> str:
    """Format a valuation ratio."""
    if val is None:
        return "—"
    return f"{val:.1f}x"


def premium_discount(company_val: float | None, sector_median: float | None) -> str:
    """Show premium/discount vs sector median."""
    if company_val is None or sector_median is None or sector_median == 0:
        return "—"
    diff_pct = ((company_val - sector_median) / abs(sector_median)) * 100
    if diff_pct > 0:
        return f"+{diff_pct:.0f}%"
    return f"{diff_pct:.0f}%"


# ── Report sections ─────────────────────────────────────────────────────────


def build_header(data: dict) -> str:
    """Build report header."""
    agg = data["sector_aggregates"]
    lines = [
        f"# {data['sector']} — Sector Overview",
        "",
        f"*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        f"*Coverage: {data['company_count']} companies in our universe*",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Companies | {data['company_count']} |",
        f"| Total Market Cap | {fmt_billions(agg.get('total_market_cap'))} |",
        f"| Median Revenue Growth | {fmt_pct(agg.get('median_revenue_growth'))} |",
        f"| Median Operating Margin | {fmt_pct(agg.get('median_operating_margin'))} |",
        f"| Median P/E | {fmt_ratio(agg.get('median_pe_ratio'))} |",
        f"| Median EV/EBITDA | {fmt_ratio(agg.get('median_ev_to_ebitda'))} |",
        f"| Median ROE | {fmt_pct(agg.get('median_roe'))} |",
        "",
    ]
    return "\n".join(lines)


def build_competitive_landscape(data: dict) -> str:
    """Build competitive comparison table."""
    companies = data["companies"]
    if not companies:
        return "## Competitive Landscape\n\nNo companies available.\n"

    lines = [
        "## Competitive Landscape",
        "",
        "| Ticker | Company | Industry | Mkt Cap | Rev Growth | Op Margin | ROE | P/E | EV/EBITDA |",
        "|--------|---------|----------|---------|------------|-----------|-----|-----|-----------|",
    ]

    for c in companies:
        m = c["metrics"]
        lines.append(
            f"| **{c['ticker']}** "
            f"| {c['name'][:30]} "
            f"| {(c.get('industry') or '')[:20]} "
            f"| {fmt_billions(c.get('market_cap'))} "
            f"| {fmt_pct(m.get('revenue_growth'))} "
            f"| {fmt_pct(m.get('operating_margin'))} "
            f"| {fmt_pct(m.get('roe'))} "
            f"| {fmt_ratio(m.get('pe_ratio'))} "
            f"| {fmt_ratio(m.get('ev_to_ebitda'))} |"
        )

    lines.append("")
    return "\n".join(lines)


def build_subsector_breakdown(data: dict) -> str:
    """Build subsector / industry grouping section."""
    subsectors = data.get("subsectors", {})
    if not subsectors:
        return ""

    # Build a lookup for quick access
    co_lookup = {c["ticker"]: c for c in data["companies"]}

    lines = [
        "## Subsector Breakdown",
        "",
    ]

    for industry, tickers in sorted(subsectors.items(), key=lambda x: -len(x[1])):
        lines.append(f"### {industry} ({len(tickers)})")
        lines.append("")
        for t in tickers:
            c = co_lookup.get(t)
            if c:
                m = c["metrics"]
                cap = fmt_billions(c.get("market_cap"))
                rev_g = fmt_pct(m.get("revenue_growth"))
                lines.append(f"- **{t}** ({c['name'][:35]}) — {cap} mkt cap, {rev_g} rev growth")
            else:
                lines.append(f"- **{t}**")
        lines.append("")

    return "\n".join(lines)


def build_valuation_context(data: dict) -> str:
    """Build valuation comparison section."""
    vr = data.get("valuation_range", {})
    agg = data["sector_aggregates"]
    companies = data["companies"]

    lines = [
        "## Valuation Context",
        "",
        "### Sector Valuation Range",
        "",
        "| Multiple | Low | Median | High |",
        "|----------|-----|--------|------|",
        f"| P/E | {fmt_ratio(vr.get('pe_low'))} | {fmt_ratio(vr.get('pe_median'))} | {fmt_ratio(vr.get('pe_high'))} |",
        f"| EV/EBITDA | {fmt_ratio(vr.get('ev_ebitda_low'))} | {fmt_ratio(vr.get('ev_ebitda_median'))} | {fmt_ratio(vr.get('ev_ebitda_high'))} |",
        "",
        "### Premium / Discount to Sector Median",
        "",
        "| Ticker | P/E | vs Median | EV/EBITDA | vs Median |",
        "|--------|-----|-----------|-----------|-----------|",
    ]

    pe_med = agg.get("median_pe_ratio")
    ev_med = agg.get("median_ev_to_ebitda")

    for c in companies:
        m = c["metrics"]
        pe = m.get("pe_ratio")
        ev = m.get("ev_to_ebitda")
        lines.append(
            f"| **{c['ticker']}** "
            f"| {fmt_ratio(pe)} "
            f"| {premium_discount(pe, pe_med)} "
            f"| {fmt_ratio(ev)} "
            f"| {premium_discount(ev, ev_med)} |"
        )

    lines.append("")
    return "\n".join(lines)


def build_growth_profitability(data: dict) -> str:
    """Build growth vs profitability comparison."""
    companies = data["companies"]

    lines = [
        "## Growth & Profitability",
        "",
        "| Ticker | Rev Growth | Gross Margin | Op Margin | Net Margin | FCF Margin | ROIC |",
        "|--------|------------|--------------|-----------|------------|------------|------|",
    ]

    for c in companies:
        m = c["metrics"]
        lines.append(
            f"| **{c['ticker']}** "
            f"| {fmt_pct(m.get('revenue_growth'))} "
            f"| {fmt_pct(m.get('gross_margin'))} "
            f"| {fmt_pct(m.get('operating_margin'))} "
            f"| {fmt_pct(m.get('net_margin'))} "
            f"| {fmt_pct(m.get('fcf_margin'))} "
            f"| {fmt_pct(m.get('roic'))} |"
        )

    lines.append("")

    # Identify outliers
    outliers = []
    for c in companies:
        m = c["metrics"]
        rg = m.get("revenue_growth")
        om = m.get("operating_margin")
        if rg is not None and om is not None:
            if rg > 0.20 and om > 0.20:
                outliers.append(
                    f"- **{c['ticker']}**: High growth ({fmt_pct(rg)}) with strong margins ({fmt_pct(om)}) — rare combination"
                )
            elif rg > 0.20 and om < 0.10:
                outliers.append(
                    f"- **{c['ticker']}**: High growth ({fmt_pct(rg)}) but thin margins ({fmt_pct(om)}) — investing for scale"
                )
            elif rg < 0.05 and om > 0.25:
                outliers.append(
                    f"- **{c['ticker']}**: Slow growth ({fmt_pct(rg)}) but very profitable ({fmt_pct(om)}) — mature cash generator"
                )

    if outliers:
        lines.append("### Notable Profiles")
        lines.append("")
        lines.extend(outliers)
        lines.append("")

    return "\n".join(lines)


def build_financial_health(data: dict) -> str:
    """Build financial health / leverage section."""
    companies = data["companies"]

    lines = [
        "## Financial Health",
        "",
        "| Ticker | Debt/Equity | Current Ratio | FCF Yield |",
        "|--------|-------------|---------------|-----------|",
    ]

    for c in companies:
        m = c["metrics"]
        lines.append(
            f"| **{c['ticker']}** "
            f"| {fmt_number(m.get('debt_to_equity'))} "
            f"| {fmt_number(m.get('current_ratio'))} "
            f"| {fmt_pct(m.get('fcf_yield'))} |"
        )

    lines.append("")
    return "\n".join(lines)


# ── Main report assembly ────────────────────────────────────────────────────


def generate_report(sector_slug: str) -> str | None:
    """Generate the full sector overview report."""
    io = ArtifactIO("_sectors", sector_slug)
    data = io.read_json("sector_data.json")

    if not data:
        print(f"ERROR: No sector_data.json found for slug '{sector_slug}'.")
        print("Run collect_sector.py first.")
        return None

    sector = data.get("sector", sector_slug)
    print(f"Generating sector overview for: {sector}")

    sections = [
        build_header(data),
        build_competitive_landscape(data),
        build_subsector_breakdown(data),
        build_valuation_context(data),
        build_growth_profitability(data),
        build_financial_health(data),
    ]

    report = "\n".join(sections)

    # Write the report
    out = io.write_text("sector_overview.md", report)
    print(f"  ✓ Wrote {out}")

    return report


def persist_report(sector: str, sector_slug: str, content_md: str) -> bool:
    """POST the report to the analysis reports endpoint."""
    payload = {
        "ticker": f"_SECTOR_{sector_slug.upper()}",
        "report_type": "sector_overview",
        "content_md": content_md,
        "metadata": {
            "sector": sector,
            "sector_slug": sector_slug,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    try:
        with httpx.Client() as client:
            r = client.post(
                f"{API_URL}/api/analysis/reports",
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            print(f"  ✓ Persisted to database")
            return True
    except (httpx.HTTPStatusError, httpx.ConnectError) as exc:
        print(f"  WARN: Could not persist report → {exc}")
        return False


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Generate a sector overview markdown report."
    )
    parser.add_argument(
        "--sector",
        type=str,
        required=True,
        help="Sector name or slug (e.g. 'Technology' or 'technology')",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Also POST the report to the analysis reports API",
    )
    args = parser.parse_args()

    sector_slug = slugify(args.sector)
    report = generate_report(sector_slug)

    if not report:
        sys.exit(1)

    if args.persist:
        # Read back to get sector name
        io = ArtifactIO("_sectors", sector_slug)
        data = io.read_json("sector_data.json")
        sector_name = data.get("sector", args.sector) if data else args.sector
        persist_report(sector_name, sector_slug, report)

    print("\nDone.")


if __name__ == "__main__":
    main()
