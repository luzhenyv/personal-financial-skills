#!/usr/bin/env python3
"""Task 2-3 — Generate earnings preview report from raw data.

Reads the raw JSON produced by collect_preview.py and renders a structured
JSON + markdown preview with trend tables and scenario placeholders.

The AI agent fills in the scenario framework and catalyst checklist
during the interactive review.

Usage::

    uv run python skills/earnings-preview/scripts/generate_preview.py NVDA
    uv run python skills/earnings-preview/scripts/generate_preview.py NVDA --quarter Q1 --year 2026
    uv run python skills/earnings-preview/scripts/generate_preview.py NVDA --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


def _find_latest_raw(io: ArtifactIO, quarter: str | None, year: int | None) -> dict | None:
    """Find the most recent preview raw JSON."""
    if quarter and year:
        return io.read_json(f"preview_{quarter}_{year}_raw.json")
    # Find latest preview_*_raw.json
    files = io.list_files("preview_*_raw.json")
    if not files:
        return None
    return io.read_json(files[-1].name)


def generate(ticker: str, quarter: str | None, year: int | None, persist: bool) -> bool:
    ticker = ticker.upper()
    io = ArtifactIO(ticker, "earnings")

    raw = _find_latest_raw(io, quarter, year)
    if not raw:
        print(f"  ✗  No raw preview data found. Run collect_preview.py first.")
        return False

    q_label = raw.get("preview_quarter", "Q?")
    q_year = raw.get("preview_year", "?")
    print(f"Generating earnings preview for {ticker} {q_label} {q_year}...")

    # Build structured preview
    preview = _build_preview(raw)
    json_path = io.write_json(f"preview_{q_label}_{q_year}.json", preview)
    print(f"  ✓  JSON written to {json_path}")

    # Build markdown
    md = _render_markdown(raw, preview)
    md_path = io.write_text(f"preview_{q_label}_{q_year}.md", md)
    print(f"  ✓  Markdown written to {md_path}")

    if persist:
        _persist_report(ticker, q_label, q_year, md)

    return True


def _build_preview(raw: dict) -> dict:
    """Build structured preview from raw data."""
    trends = raw.get("trends", {})
    thesis = raw.get("thesis_context")

    # Quarter-over-quarter table from quarterly data
    quarterly = raw.get("quarterly_data", [])
    quarterly_summary = []
    for q in quarterly[-4:]:  # Last 4 quarters
        inc = q.get("income_statement") or q.get("income", {}) or {}
        quarterly_summary.append({
            "quarter": f"Q{q.get('fiscal_quarter', '?')} {q.get('fiscal_year', '?')}",
            "revenue": inc.get("total_revenue") or inc.get("revenue"),
            "eps": inc.get("eps_diluted") or inc.get("eps"),
            "gross_margin": None,
            "op_margin": None,
        })
        rev = inc.get("total_revenue") or inc.get("revenue")
        if rev and inc.get("gross_profit"):
            quarterly_summary[-1]["gross_margin"] = round(inc["gross_profit"] / rev, 4)
        if rev and inc.get("operating_income"):
            quarterly_summary[-1]["op_margin"] = round(inc["operating_income"] / rev, 4)

    # Price context
    prices = raw.get("recent_prices", [])
    price_context = {}
    if prices:
        closes = [p.get("close") or p.get("close_price") for p in prices if p.get("close") or p.get("close_price")]
        if closes:
            price_context = {
                "current": closes[-1],
                "3mo_high": max(closes),
                "3mo_low": min(closes),
                "3mo_change_pct": round((closes[-1] - closes[0]) / closes[0], 4) if closes[0] else None,
            }

    return {
        "ticker": raw["ticker"],
        "company_name": raw.get("company_name", ""),
        "preview_quarter": raw["preview_quarter"],
        "preview_year": raw["preview_year"],
        "quarterly_summary": quarterly_summary,
        "trends": trends,
        "price_context": price_context,
        "thesis_context_available": thesis is not None,
        "scenarios": {
            "bull": {"revenue": None, "eps": None, "key_driver": "", "stock_reaction": ""},
            "base": {"revenue": None, "eps": None, "key_driver": "", "stock_reaction": ""},
            "bear": {"revenue": None, "eps": None, "key_driver": "", "stock_reaction": ""},
        },
        "catalyst_checklist": [],
        "ai_generated": False,
    }


def _render_markdown(raw: dict, preview: dict) -> str:
    """Render preview as readable markdown."""
    ticker = raw["ticker"]
    q = raw["preview_quarter"]
    yr = raw["preview_year"]
    lines = [
        f"# Earnings Preview: {ticker} — {q} {yr}",
        "",
        f"**Company:** {raw.get('company_name', ticker)}  ",
        f"**Sector:** {raw.get('sector', 'N/A')} | **Industry:** {raw.get('industry', 'N/A')}",
        "",
    ]

    # Price context
    pc = preview.get("price_context", {})
    if pc:
        lines.append("## Recent Price Action")
        lines.append("")
        lines.append(f"- Current: ${pc.get('current', 'N/A')}")
        lines.append(f"- 3-month range: ${pc.get('3mo_low', '?')} — ${pc.get('3mo_high', '?')}")
        chg = pc.get("3mo_change_pct")
        if chg is not None:
            lines.append(f"- 3-month change: {chg:.1%}")
        lines.append("")

    # Quarterly trend table
    qs = preview.get("quarterly_summary", [])
    if qs:
        lines.append("## Quarterly Trends")
        lines.append("")
        lines.append("| Quarter | Revenue | EPS | Gross Margin | Op Margin |")
        lines.append("|---------|---------|-----|-------------|-----------|")
        for q_row in qs:
            rev = f"${q_row['revenue']:,.0f}" if q_row.get("revenue") else "N/A"
            eps = f"${q_row['eps']:.2f}" if q_row.get("eps") else "N/A"
            gm = f"{q_row['gross_margin']:.1%}" if q_row.get("gross_margin") else "N/A"
            om = f"{q_row['op_margin']:.1%}" if q_row.get("op_margin") else "N/A"
            lines.append(f"| {q_row['quarter']} | {rev} | {eps} | {gm} | {om} |")
        lines.append("")

    # Growth trends
    trends = raw.get("trends", {})
    if trends:
        lines.append("## Growth Trends")
        lines.append("")
        yoy = trends.get("yoy_revenue_growth")
        seq = trends.get("sequential_revenue_growth")
        if yoy is not None:
            lines.append(f"- **YoY revenue growth**: {yoy:.1%}")
        if seq is not None:
            lines.append(f"- **Sequential revenue growth**: {seq:.1%}")
        lines.append("")

    # Segments
    segs = raw.get("segments", {})
    if segs and isinstance(segs, dict):
        for seg_type, entries in segs.items():
            if isinstance(entries, list) and entries:
                lines.append(f"### Segments — {seg_type}")
                lines.append("")
                for s in entries[:10]:
                    name = s.get("segment") or s.get("name", "?")
                    val = s.get("value") or s.get("revenue")
                    if val:
                        lines.append(f"- **{name}**: ${val:,.0f}")
                lines.append("")

    # Scenario framework placeholder
    lines.append("## Scenario Framework")
    lines.append("")
    lines.append("*To be filled by AI agent — run scenario analysis on the collected data.*")
    lines.append("")
    lines.append("| Scenario | Revenue | EPS | Key Driver | Expected Stock Reaction |")
    lines.append("|----------|---------|-----|------------|------------------------|")
    lines.append("| 🟢 Bull | | | | |")
    lines.append("| ⚪ Base | | | | |")
    lines.append("| 🔴 Bear | | | | |")
    lines.append("")

    # Catalyst checklist placeholder
    lines.append("## Key Metrics & Catalyst Checklist")
    lines.append("")
    lines.append("*To be filled by AI agent — identify the 3-5 things that determine the stock reaction.*")
    lines.append("")
    lines.append("1. [ ] ")
    lines.append("2. [ ] ")
    lines.append("3. [ ] ")
    lines.append("")

    # Thesis context
    thesis = raw.get("thesis_context")
    if thesis:
        lines.append("## Thesis Context")
        lines.append("")
        lines.append(f"**Thesis:** {thesis.get('thesis_statement', 'N/A')}")
        lines.append(f"**Position:** {thesis.get('position', 'N/A')} | **Conviction:** {thesis.get('conviction', 'N/A')}")
        score = thesis.get("latest_health_score")
        if score:
            lines.append(f"**Latest health score:** {score}")
        lines.append("")
        assumptions = thesis.get("assumptions", [])
        if assumptions:
            lines.append("### Assumptions to Watch")
            lines.append("")
            for a in assumptions:
                title = a.get("title", "") or a.get("name", "")
                weight = a.get("weight", 0)
                lines.append(f"- **{title}** (weight: {weight}%)")
            lines.append("")

    # Upcoming catalysts
    catalysts = raw.get("catalysts", [])
    if catalysts:
        lines.append("## Upcoming Catalysts")
        lines.append("")
        for c in catalysts[:5]:
            evt = c.get("event", "?")
            dt = c.get("date", "?")
            impact = c.get("expected_impact", "?")
            lines.append(f"- **{evt}** ({dt}) — expected impact: {impact}")
        lines.append("")

    return "\n".join(lines)


def _persist_report(ticker: str, q_label: str, q_year: int, md: str) -> None:
    try:
        resp = httpx.post(
            f"{API_URL}/api/analysis/reports",
            json={
                "ticker": ticker,
                "report_type": "earnings_preview",
                "title": f"{ticker} Earnings Preview — {q_label} {q_year}",
                "content_md": md,
                "generated_by": "earnings-preview",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        print(f"  ✓  Report persisted to database")
    except Exception as exc:
        print(f"  ⚠  Could not persist: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate earnings preview report")
    parser.add_argument("ticker", help="Company ticker")
    parser.add_argument("--quarter", help="Quarter (e.g. Q1)")
    parser.add_argument("--year", type=int, help="Fiscal year")
    parser.add_argument("--persist", action="store_true", help="Persist to database")
    args = parser.parse_args()

    success = generate(args.ticker, args.quarter, args.year, args.persist)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
