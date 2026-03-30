"""
Task 4: Generate Earnings Analysis Report
==========================================
Reads the raw earnings data JSON (from collect_earnings.py) and assembles
a structured JSON artifact + markdown narrative report.

The AI agent is expected to run Tasks 2-3 (beat/miss analysis, thesis impact)
and write the analysis JSON before running this script.  If the analysis JSON
is missing, the script builds a data-only report from the raw collection.

Usage:
    uv run python skills/earnings-analysis/scripts/generate_earnings_report.py NVDA
    uv run python skills/earnings-analysis/scripts/generate_earnings_report.py NVDA --quarter Q4 --year 2024
    uv run python skills/earnings-analysis/scripts/generate_earnings_report.py NVDA --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import Any

import httpx

from artifact_io import ArtifactIO

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")


# ── Formatting helpers ───────────────────────────────────────────────────────

def _fmt_num(val: Any, prefix: str = "$", suffix: str = "", decimals: int = 1) -> str:
    """Format a number in billions/millions with prefix."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return "N/A"
    abs_v = abs(v)
    if abs_v >= 1e9:
        return f"{prefix}{v / 1e9:,.{decimals}f}B{suffix}"
    if abs_v >= 1e6:
        return f"{prefix}{v / 1e6:,.{decimals}f}M{suffix}"
    return f"{prefix}{v:,.{decimals}f}{suffix}"


def _fmt_pct(val: Any, decimals: int = 1) -> str:
    """Format a percentage value."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):+.{decimals}f}%"
    except (ValueError, TypeError):
        return "N/A"


def _pct_change(current: Any, prior: Any) -> float | None:
    """Calculate percent change between two values."""
    try:
        c, p = float(current), float(prior)
        if p == 0:
            return None
        return ((c - p) / abs(p)) * 100
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# ── Beat/Miss table builder ─────────────────────────────────────────────────

def _build_beat_miss_table(quarterly: list[dict], quarter: str, year: int) -> str:
    """Build a beat/miss summary table from quarterly data."""
    q_num = int(quarter.replace("Q", ""))

    # Find the target quarter and comparables
    target = None
    prior_q = None  # QoQ
    yoy_q = None    # YoY

    for q in quarterly:
        fy = q.get("fiscal_year")
        fq = q.get("fiscal_quarter")
        if fy == year and fq == q_num:
            target = q
        elif fy == year and fq == q_num - 1:
            prior_q = q
        elif fy == year - 1 and fq == q_num:
            yoy_q = q
    # If Q1, prior quarter is Q4 of previous year
    if q_num == 1:
        for q in quarterly:
            if q.get("fiscal_year") == year - 1 and q.get("fiscal_quarter") == 4:
                prior_q = q
                break

    if not target:
        return "_No matching quarterly data found for the target period._\n"

    metrics = [
        ("Revenue", "revenue"),
        ("Gross Profit", "gross_profit"),
        ("Operating Income", "operating_income"),
        ("Net Income", "net_income"),
        ("EPS (Diluted)", "eps_diluted"),
    ]

    lines = [
        "| Metric | Result | QoQ Change | YoY Change |",
        "|--------|--------|------------|------------|",
    ]

    for label, key in metrics:
        val = target.get(key)
        is_eps = key == "eps_diluted"
        fmt_val = f"${float(val):.2f}" if is_eps and val is not None else _fmt_num(val)

        qoq = _pct_change(val, prior_q.get(key) if prior_q else None)
        yoy = _pct_change(val, yoy_q.get(key) if yoy_q else None)

        lines.append(
            f"| {label} | {fmt_val} | {_fmt_pct(qoq)} | {_fmt_pct(yoy)} |"
        )

    return "\n".join(lines) + "\n"


# ── Margin analysis builder ─────────────────────────────────────────────────

def _build_margin_analysis(quarterly: list[dict]) -> str:
    """Build margin trend table from quarterly data."""
    if not quarterly:
        return "_No quarterly data available for margin analysis._\n"

    lines = [
        "| Quarter | Gross Margin | Operating Margin | Net Margin |",
        "|---------|-------------|-----------------|------------|",
    ]

    for q in quarterly[-8:]:  # Last 8 quarters
        fq = q.get("fiscal_quarter")
        fy = q.get("fiscal_year")
        rev = _safe_float(q.get("revenue"))

        gp = _safe_float(q.get("gross_profit"))
        oi = _safe_float(q.get("operating_income"))
        ni = _safe_float(q.get("net_income"))

        gm = f"{gp / rev * 100:.1f}%" if rev and gp else "N/A"
        om = f"{oi / rev * 100:.1f}%" if rev and oi else "N/A"
        nm = f"{ni / rev * 100:.1f}%" if rev and ni else "N/A"

        lines.append(f"| Q{fq} FY{fy} | {gm} | {om} | {nm} |")

    return "\n".join(lines) + "\n"


# ── Segment breakdown builder ───────────────────────────────────────────────

def _build_segment_table(segments: list[dict]) -> str:
    """Build segment revenue breakdown table."""
    if not segments:
        return "_No segment data available._\n"

    # Group by segment type
    by_type: dict[str, list[dict]] = {}
    for s in segments:
        st = s.get("segment_type", "other")
        by_type.setdefault(st, []).append(s)

    parts = []
    for seg_type, items in by_type.items():
        lines = [
            f"**{seg_type.replace('_', ' ').title()}**\n",
            "| Segment | Revenue | Year |",
            "|---------|---------|------|",
        ]
        for item in sorted(items, key=lambda x: (x.get("fiscal_year", 0), x.get("segment_name", ""))):
            lines.append(
                f"| {item.get('segment_name', 'N/A')} "
                f"| {_fmt_num(item.get('revenue'))} "
                f"| FY{item.get('fiscal_year', 'N/A')} |"
            )
        parts.append("\n".join(lines))

    return "\n\n".join(parts) + "\n"


# ── Thesis impact section ───────────────────────────────────────────────────

def _build_thesis_section(thesis_summary: dict | None) -> str:
    """Build thesis impact section from thesis data."""
    if not thesis_summary:
        return (
            "_No investment thesis is currently tracked for this company._\n\n"
            "Consider creating one:\n"
            "```bash\n"
            "uv run python skills/thesis-tracker/scripts/thesis_cli.py create {TICKER} --interactive\n"
            "```\n"
        )

    lines = [
        f"**Thesis**: {thesis_summary.get('statement', 'N/A')}\n",
        f"**Current Health Score**: {thesis_summary.get('health_score', 'N/A')}\n",
    ]

    pillars = thesis_summary.get("pillars", [])
    if pillars:
        lines.append("**Key Pillars:**")
        for p in pillars:
            lines.append(f"- {p}")

    lines.append(
        "\n> **Action Required**: Review thesis assumptions against this quarter's "
        "results using `thesis_cli.py update`."
    )
    return "\n".join(lines) + "\n"


# ── Main report assembly ────────────────────────────────────────────────────

def generate_report(ticker: str, quarter: str | None, year: int | None, persist: bool) -> bool:
    """Generate the earnings analysis report from collected data.

    Returns True on success, False on failure.
    """
    ticker = ticker.upper()
    io = ArtifactIO(ticker, "earnings")

    # ── Find the raw data file ───────────────────────────────────────────
    raw_files = io.list_files("*_raw.json")
    if not raw_files:
        print(f"✗ No raw data found. Run collect_earnings.py first:")
        print(f"  uv run python skills/earnings-analysis/scripts/collect_earnings.py {ticker}")
        return False

    # If quarter/year specified, look for exact match; otherwise use latest
    if quarter and year:
        target_name = f"{quarter}_{year}_raw.json"
        raw_data = io.read_json(target_name)
        if not raw_data:
            print(f"✗ {target_name} not found. Available:")
            for f in raw_files:
                print(f"  - {f.name}")
            return False
    else:
        raw_data = io.read_json(raw_files[-1].name)
        quarter = raw_data.get("quarter", "Q?")
        year = raw_data.get("fiscal_year", date.today().year)

    print(f"\n{'='*60}")
    print(f"  Generating Earnings Report: {ticker} {quarter} FY{year}")
    print(f"{'='*60}\n")

    company = raw_data.get("company", {})
    quarterly = raw_data.get("quarterly_data", [])
    segments = raw_data.get("segments", [])
    metrics = raw_data.get("metrics", [])
    thesis_summary = raw_data.get("thesis_summary")
    latest_10q = raw_data.get("latest_10q")
    freshness = raw_data.get("freshness_check", "unknown")

    company_name = company.get("name", ticker)

    # ── Check for AI-enriched analysis (from Tasks 2-3) ──────────────────
    analysis_file = f"{quarter}_{year}_analysis_data.json"
    analysis = io.read_json(analysis_file)
    if analysis:
        print(f"  ✓ Found AI analysis: {analysis_file}")
    else:
        print(f"  — No AI analysis found ({analysis_file}). Building data-only report.")

    # ── Build structured JSON artifact ───────────────────────────────────

    q_num = int(quarter.replace("Q", ""))
    target_q = None
    for q in quarterly:
        if q.get("fiscal_year") == year and q.get("fiscal_quarter") == q_num:
            target_q = q
            break

    earnings_json: dict[str, Any] = {
        "ticker": ticker,
        "company_name": company_name,
        "quarter": quarter,
        "fiscal_year": year,
        "analysis_date": date.today().isoformat(),
        "freshness_check": freshness,
        "filing": {
            "form_type": "10-Q",
            "filing_date": latest_10q.get("filing_date") if latest_10q else None,
            "filing_id": latest_10q.get("id") if latest_10q else None,
        },
        "results": {},
        "thesis_impact": analysis.get("thesis_impact") if analysis else None,
        "recommendation": analysis.get("recommendation") if analysis else None,
    }

    if target_q:
        earnings_json["results"] = {
            "revenue": target_q.get("revenue"),
            "gross_profit": target_q.get("gross_profit"),
            "operating_income": target_q.get("operating_income"),
            "net_income": target_q.get("net_income"),
            "eps_diluted": target_q.get("eps_diluted"),
            "shares_diluted": target_q.get("shares_diluted"),
        }

    json_path = io.write_json(f"{quarter}_{year}.json", earnings_json)
    print(f"  ✓ Written: {json_path.name}")

    # ── Build markdown report ────────────────────────────────────────────

    rev = target_q.get("revenue") if target_q else None
    eps = target_q.get("eps_diluted") if target_q else None

    # Find YoY quarter for summary
    yoy_q = None
    for q in quarterly:
        if q.get("fiscal_year") == year - 1 and q.get("fiscal_quarter") == q_num:
            yoy_q = q
            break
    rev_yoy = _pct_change(rev, yoy_q.get("revenue") if yoy_q else None)
    eps_yoy = _pct_change(eps, yoy_q.get("eps_diluted") if yoy_q else None)

    rec = "Under Review"
    if analysis:
        rec = analysis.get("recommendation", "Under Review")

    freshness_note = ""
    if freshness == "stale":
        freshness_note = "\n> ⚠️ **Data may not reflect the latest quarter.** Re-run ETL to refresh.\n"

    md_parts = [
        f"# {company_name} — {quarter} FY{year} Earnings Analysis\n",
        freshness_note,
        "## Quick Summary\n",
        f"- **Quarter**: {quarter} FY{year}",
        f"- **Revenue**: {_fmt_num(rev)} (YoY {_fmt_pct(rev_yoy)})",
        f"- **EPS (Diluted)**: ${float(eps):.2f} (YoY {_fmt_pct(eps_yoy)})" if eps else "- **EPS**: N/A",
        f"- **Recommendation**: {rec}",
        f"- **Analysis Date**: {date.today().isoformat()}\n",

        "## Beat/Miss Summary\n",
        _build_beat_miss_table(quarterly, quarter, year),

        "\n## Margin Analysis\n",
        _build_margin_analysis(quarterly),

        "\n## Revenue Breakdown by Segment\n",
        _build_segment_table(segments),
    ]

    # Guidance section (from AI analysis if available)
    if analysis and analysis.get("guidance"):
        md_parts.append("\n## Guidance Update\n")
        md_parts.append(analysis["guidance"] + "\n")
    else:
        md_parts.append("\n## Guidance Update\n")
        md_parts.append("_Guidance analysis requires AI review of the earnings release and call transcript._\n")

    # Thesis impact
    md_parts.append("\n## Thesis Impact Assessment\n")
    if analysis and analysis.get("thesis_impact_narrative"):
        md_parts.append(analysis["thesis_impact_narrative"] + "\n")
    else:
        md_parts.append(_build_thesis_section(thesis_summary))

    # Key takeaways
    if analysis and analysis.get("key_takeaways"):
        md_parts.append("\n## Key Takeaways\n")
        for i, t in enumerate(analysis["key_takeaways"], 1):
            md_parts.append(f"{i}. {t}")
        md_parts.append("")

    # Data sources
    md_parts.extend([
        "\n## Data Sources\n",
        f"- REST API: `/api/financials/{ticker}/quarterly`",
        f"- REST API: `/api/financials/{ticker}/segments`",
        f"- REST API: `/api/financials/{ticker}/metrics`",
    ])
    if latest_10q:
        md_parts.append(
            f"- SEC Filing: 10-Q filed {latest_10q.get('filing_date', 'N/A')} "
            f"(ID: {latest_10q.get('id', 'N/A')})"
        )
    md_parts.append(f"- Analysis date: {date.today().isoformat()}\n")

    report_md = "\n".join(md_parts)

    md_path = io.write_text(f"{quarter}_{year}_analysis.md", report_md)
    print(f"  ✓ Written: {md_path.name}")

    # ── Persist to DB if requested ───────────────────────────────────────

    if persist:
        print("\n  Persisting report to database...")
        try:
            resp = httpx.post(
                f"{API_URL}/api/analysis/reports",
                json={
                    "ticker": ticker,
                    "report_type": "earnings_analysis",
                    "title": f"{company_name} — {quarter} FY{year} Earnings Analysis",
                    "content_md": report_md,
                    "file_path": str(md_path),
                    "generated_by": "earnings-analysis-skill",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                print("  ✓ Report persisted to database")
            else:
                print(f"  ⚠ Failed to persist: {resp.status_code} {resp.text[:200]}")
        except httpx.HTTPError as e:
            print(f"  ⚠ API unavailable for persistence: {e}")

    print(f"\n{'='*60}")
    print(f"  ✓ Earnings report complete: {ticker} {quarter} FY{year}")
    print(f"  Artifacts: {io.path}")
    print(f"{'='*60}\n")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate earnings analysis report from collected data.",
    )
    parser.add_argument("ticker", help="Company ticker (e.g. NVDA)")
    parser.add_argument("--quarter", help="Quarter label (e.g. Q4). Auto-detected if omitted.")
    parser.add_argument("--year", type=int, help="Fiscal year (e.g. 2024). Auto-detected if omitted.")
    parser.add_argument("--persist", action="store_true",
                        help="Persist report to database via POST /api/analysis/reports")
    args = parser.parse_args()

    success = generate_report(args.ticker, args.quarter, args.year, args.persist)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
