#!/usr/bin/env python3
"""Idea Generation — Generate Markdown Report from Screen Results.

Reads screen_results.json and produces a formatted markdown report
with one-page summaries per idea candidate.

Usage::

    uv run python skills/idea-generation/scripts/generate_ideas.py
    uv run python skills/idea-generation/scripts/generate_ideas.py --top 10
    uv run python skills/idea-generation/scripts/generate_ideas.py --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── Path setup ───────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO, read_artifact_json

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30

io = ArtifactIO("_ideas", "")


def _get(client: httpx.Client, path: str, **params: object) -> dict | list | None:
    """GET helper — returns parsed JSON or None on error."""
    try:
        resp = client.get(path, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError:
        return None
    except httpx.ConnectError:
        return None


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val * 100:.1f}%"


def _fmt_ratio(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.1f}x"


def _fmt_num(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.2f}"


def _build_idea_section(result: dict, rank: int, extra: dict | None = None) -> str:
    """Build a markdown section for one idea candidate."""
    m = result.get("metrics", {})
    flags = result.get("flags", [])

    lines = [
        f"### {rank}. {result['ticker']} — {result['name']}",
        "",
        f"**Sector:** {result.get('sector', '—')} | "
        f"**Score:** {result.get('score', 0):.1f}/100 | "
        f"**Screen:** {result.get('screen_type', '—')}",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Revenue Growth | {_fmt_pct(m.get('revenue_growth'))} |",
        f"| EPS Growth | {_fmt_pct(m.get('eps_growth'))} |",
        f"| Operating Margin | {_fmt_pct(m.get('operating_margin'))} |",
        f"| Net Margin | {_fmt_pct(m.get('net_margin'))} |",
        f"| ROE | {_fmt_pct(m.get('roe'))} |",
        f"| ROIC | {_fmt_pct(m.get('roic'))} |",
        f"| P/E | {_fmt_ratio(m.get('pe_ratio'))} |",
        f"| EV/EBITDA | {_fmt_ratio(m.get('ev_to_ebitda'))} |",
        f"| P/B | {_fmt_ratio(m.get('pb_ratio'))} |",
        f"| FCF Yield | {_fmt_pct(m.get('fcf_yield'))} |",
        f"| Debt/Equity | {_fmt_num(m.get('debt_to_equity'))} |",
        "",
    ]

    if flags:
        lines.append(f"**Flags:** {', '.join(flags)}")
        lines.append("")

    # Add extra context if available
    if extra:
        company = extra.get("company", {})
        if company.get("description"):
            desc = company["description"]
            # Truncate to ~200 chars
            if len(desc) > 200:
                desc = desc[:200].rsplit(" ", 1)[0] + "…"
            lines.append(f"**Description:** {desc}")
            lines.append("")

        if company.get("market_cap"):
            mc = company["market_cap"]
            if mc >= 1_000_000_000_000:
                mc_str = f"${mc / 1_000_000_000_000:.1f}T"
            elif mc >= 1_000_000_000:
                mc_str = f"${mc / 1_000_000_000:.1f}B"
            else:
                mc_str = f"${mc / 1_000_000:.0f}M"
            lines.append(f"**Market Cap:** {mc_str}")
            lines.append("")

    # Thesis hint (may be empty — populated by AI or manually)
    hint = result.get("thesis_hint", "")
    if hint:
        lines.append(f"**Thesis Hint:** {hint}")
        lines.append("")

    lines.append("**Suggested Next Steps:** Run company profile → create thesis if compelling")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def generate_report(top_n: int = 10) -> str:
    """Generate a markdown report from the latest screen results."""
    data = io.read_json("screen_results.json")
    if not data:
        print("  ✗  No screen_results.json found. Run screen.py first.", file=sys.stderr)
        sys.exit(1)

    results = data.get("results", [])
    screen_type = data.get("screen_type", "unknown")
    screened_at = data.get("screened_at", "—")
    total = data.get("total_companies", 0)
    passes = data.get("passes", 0)

    top_results = results[:top_n]

    # Fetch extra company details for top results
    extras: dict[str, dict] = {}
    with httpx.Client(base_url=API_URL) as client:
        for r in top_results:
            ticker = r["ticker"]
            company_data = _get(client, f"/api/companies/{ticker}")
            if company_data:
                extras[ticker] = {"company": company_data}

    # Build report
    lines = [
        "# Idea Generation — Screen Results",
        "",
        f"**Screen Type:** {screen_type} | "
        f"**Date:** {screened_at[:10] if len(screened_at) >= 10 else screened_at} | "
        f"**Passed:** {passes}/{total} companies",
        "",
    ]

    # Summary of filters
    params = data.get("screen_params", {})
    filters = params.get("filters", [])
    if filters:
        lines.append("**Filters Applied:**")
        for f in filters:
            lines.append(f"- {f['metric']} {f['op']} {f['threshold']}")
        lines.append("")

    lines.append("---")
    lines.append("")

    if not top_results:
        lines.append("*No companies passed the screen criteria.*")
    else:
        # Comparison table
        lines.append("## Quick Comparison")
        lines.append("")
        lines.append("| # | Ticker | Sector | Score | Rev Growth | Op Margin | P/E | FCF Yield |")
        lines.append("|---|--------|--------|-------|-----------|-----------|-----|-----------|")
        for i, r in enumerate(top_results, 1):
            m = r.get("metrics", {})
            lines.append(
                f"| {i} | **{r['ticker']}** | {r.get('sector', '—')} | "
                f"{r.get('score', 0):.0f} | "
                f"{_fmt_pct(m.get('revenue_growth'))} | "
                f"{_fmt_pct(m.get('operating_margin'))} | "
                f"{_fmt_ratio(m.get('pe_ratio'))} | "
                f"{_fmt_pct(m.get('fcf_yield'))} |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")

        # Detail sections
        lines.append("## Idea Details")
        lines.append("")
        for i, r in enumerate(top_results, 1):
            extra = extras.get(r["ticker"])
            lines.append(_build_idea_section(r, i, extra))

    lines.append(f"\n*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate idea report from screen results",
    )
    parser.add_argument("--top", type=int, default=10, help="Number of top ideas to include")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Also upsert report to database via POST /api/analysis/reports",
    )
    args = parser.parse_args()

    print("\n  Generating idea report…")
    report_md = generate_report(top_n=args.top)

    path = io.write_text("screen_results.md", report_md)
    print(f"  ✓  Wrote {path}")

    if args.persist:
        print("  Persisting to database…")
        with httpx.Client(base_url=API_URL) as client:
            try:
                resp = client.post(
                    "/api/analysis/reports",
                    json={
                        "ticker": "_IDEAS",
                        "report_type": "idea_screen",
                        "title": "Idea Generation Screen Results",
                        "content_md": report_md,
                        "file_path": str(path),
                        "generated_by": "idea-generation",
                    },
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                print("  ✓  Persisted to database")
            except httpx.HTTPStatusError as exc:
                print(f"  ⚠  Failed to persist: {exc.response.status_code}", file=sys.stderr)
            except httpx.ConnectError:
                print(f"  ⚠  Cannot reach API — report saved locally only", file=sys.stderr)

    print()


if __name__ == "__main__":
    main()
