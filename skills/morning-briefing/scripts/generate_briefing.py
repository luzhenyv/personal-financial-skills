#!/usr/bin/env python3
"""Task 2 — Generate morning briefing markdown from raw data.

Reads the daily raw JSON and produces a concise, opinionated briefing
readable in under 2 minutes.

Usage::

    uv run python skills/morning-briefing/scripts/generate_briefing.py
    uv run python skills/morning-briefing/scripts/generate_briefing.py --date 2026-03-28
    uv run python skills/morning-briefing/scripts/generate_briefing.py --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


def generate(briefing_date: date, persist: bool) -> bool:
    date_str = briefing_date.isoformat()
    io = ArtifactIO("_daily", "briefings")

    raw = io.read_json(f"{date_str}_raw.json")
    if not raw:
        print(f"  ✗  No raw data for {date_str}. Run collect_briefing.py first.")
        return False

    print(f"Generating morning briefing for {date_str}...")
    md = _render_markdown(raw)
    md_path = io.write_text(f"{date_str}.md", md)
    print(f"  ✓  Briefing written to {md_path}")

    if persist:
        _persist_report(date_str, md)

    return True


def _render_markdown(raw: dict) -> str:
    d = raw.get("date", "?")
    summary = raw.get("portfolio_summary", {})
    positions = raw.get("positions", [])
    movers = raw.get("notable_movers", [])
    catalysts = raw.get("upcoming_catalysts", [])
    alerts = raw.get("recent_risk_alerts", [])
    actions = raw.get("action_items", [])

    lines = [f"# Morning Briefing — {d}", ""]

    # Portfolio snapshot
    total_val = summary.get("total_value", 0)
    pnl = summary.get("unrealized_pnl", 0)
    pnl_pct = summary.get("unrealized_pnl_pct", 0)
    cash = summary.get("cash", 0)
    n_pos = summary.get("position_count", len(positions))

    lines.append("## Portfolio Snapshot")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total value | ${total_val:,.0f} |")
    lines.append(f"| Unrealized P&L | ${pnl:,.0f} ({pnl_pct:.1f}%) |")
    lines.append(f"| Cash | ${cash:,.0f} |")
    lines.append(f"| Positions | {n_pos} |")
    lines.append("")

    # Notable movers
    if movers:
        lines.append("## Notable Movers")
        lines.append("")
        lines.append("| Ticker | Daily Change | Weight |")
        lines.append("|--------|-------------|--------|")
        for m in movers[:5]:
            chg = m.get("daily_change_pct", 0)
            arrow = "📈" if chg > 0 else "📉"
            lines.append(
                f"| {m['ticker']} | {arrow} {chg:+.1%} | {m.get('weight', 0):.1f}% |"
            )
        lines.append("")
    else:
        lines.append("## Notable Movers")
        lines.append("")
        lines.append("No positions moved more than ±2% yesterday.")
        lines.append("")

    # Catalyst calendar
    lines.append("## Upcoming Catalysts")
    lines.append("")
    if catalysts:
        for c in catalysts[:7]:
            ticker = c.get("ticker", "?")
            event = c.get("event", "?")
            cat_date = c.get("date", "?")
            impact = c.get("expected_impact", "")
            lines.append(f"- **{cat_date}** — {ticker}: {event}" + (f" ({impact})" if impact else ""))
        lines.append("")
    else:
        lines.append("No upcoming catalysts on calendar.")
        lines.append("")

    # Risk alerts
    if alerts:
        lines.append("## Risk Alerts")
        lines.append("")
        for a in alerts:
            sev = a.get("severity", "info")
            icon = "🔴" if sev == "critical" else "🟡"
            lines.append(f"- {icon} **[{a.get('type', '?')}]** {a.get('message', '')}")
        lines.append("")

    # Action items
    if actions:
        lines.append("## Action Items")
        lines.append("")
        for i, a in enumerate(actions, 1):
            lines.append(f"{i}. {a}")
        lines.append("")

    # Top positions table
    if positions:
        lines.append("## Positions Overview")
        lines.append("")
        lines.append("| Ticker | Weight | P&L | P&L % |")
        lines.append("|--------|--------|-----|-------|")
        for p in sorted(positions, key=lambda x: -x.get("weight", 0))[:10]:
            pnl_val = p.get("unrealized_pnl", 0)
            pnl_p = p.get("unrealized_pnl_pct", 0)
            lines.append(
                f"| {p['ticker']} | {p.get('weight', 0):.1f}% | ${pnl_val:,.0f} | {pnl_p:+.1f}% |"
            )
        lines.append("")

    return "\n".join(lines)


def _persist_report(date_str: str, md: str) -> None:
    try:
        resp = httpx.post(
            f"{API_URL}/api/analysis/reports",
            json={
                "ticker": "_DAILY",
                "report_type": "morning_briefing",
                "title": f"Morning Briefing — {date_str}",
                "content_md": md,
                "generated_by": "morning-briefing",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        print(f"  ✓  Briefing persisted to database")
    except Exception as exc:
        print(f"  ⚠  Could not persist: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate morning briefing")
    parser.add_argument("--date", help="Briefing date (YYYY-MM-DD, default: today)")
    parser.add_argument("--persist", action="store_true", help="Persist to database")
    args = parser.parse_args()

    d = date.fromisoformat(args.date) if args.date else date.today()
    success = generate(d, args.persist)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
