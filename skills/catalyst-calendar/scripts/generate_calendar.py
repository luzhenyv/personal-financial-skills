#!/usr/bin/env python3
"""Catalyst Calendar — Generate Formatted Calendar Report.

Reads calendar.json and produces a markdown report with weekly
and monthly views, impact highlights, and action items.

Usage::

    uv run python skills/catalyst-calendar/scripts/generate_calendar.py
    uv run python skills/catalyst-calendar/scripts/generate_calendar.py --weekly
    uv run python skills/catalyst-calendar/scripts/generate_calendar.py --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

# ── Path setup ───────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30

io = ArtifactIO("_portfolio", "catalysts")


# ── Helpers ──────────────────────────────────────────────────

IMPACT_ICONS = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
TYPE_ICONS = {
    "earnings": "📊",
    "corporate": "🏢",
    "macro": "🌍",
    "regulatory": "⚖️",
    "conference": "🎤",
    "filing": "📄",
}


def _week_label(iso_week: str) -> str:
    """Convert ISO week to a readable date range label."""
    try:
        # Parse YYYY-Www
        parts = iso_week.split("-W")
        year = int(parts[0])
        week = int(parts[1])
        # Monday of that week
        monday = date.fromisocalendar(year, week, 1)
        friday = monday + timedelta(days=4)
        return f"{monday.strftime('%b %d')} – {friday.strftime('%b %d, %Y')}"
    except (ValueError, IndexError):
        return iso_week


def _is_this_week(iso_week: str) -> bool:
    """Check if the ISO week is the current week."""
    today = date.today()
    current = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
    return iso_week == current


def _is_next_week(iso_week: str) -> bool:
    """Check if the ISO week is next week."""
    next_w = date.today() + timedelta(days=7)
    nw = f"{next_w.isocalendar().year}-W{next_w.isocalendar().week:02d}"
    return iso_week == nw


# ── Report generation ────────────────────────────────────────


def generate_weekly_preview(data: dict) -> str:
    """Generate a compact weekly preview section."""
    by_week = data.get("by_week", {})
    lines: list[str] = []

    for week_key in sorted(by_week.keys()):
        events = by_week[week_key]
        label = _week_label(week_key)

        tag = ""
        if _is_this_week(week_key):
            tag = " ← **THIS WEEK**"
        elif _is_next_week(week_key):
            tag = " ← *next week*"

        lines.append(f"### {week_key}: {label}{tag}")
        lines.append("")

        for e in sorted(events, key=lambda x: x.get("date", "")):
            type_icon = TYPE_ICONS.get(e.get("type", ""), "•")
            ticker_str = f" **[{e['ticker']}]**" if e.get("ticker") else ""
            lines.append(f"- {e['date']}  {type_icon}{ticker_str} {e['event']}")

        lines.append("")

    return "\n".join(lines)


def generate_full_report(data: dict) -> str:
    """Generate the full calendar markdown report."""
    events = data.get("events", [])
    by_week = data.get("by_week", {})
    by_type = data.get("by_type", {})
    horizon_start = data.get("horizon_start", "")
    horizon_end = data.get("horizon_end", "")
    total = data.get("total_events", 0)

    lines = [
        "# Catalyst Calendar",
        "",
        f"**Period:** {horizon_start} → {horizon_end} | "
        f"**Total Events:** {total}",
        "",
    ]

    # Summary by type
    if by_type:
        lines.append("## Event Summary")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
            icon = TYPE_ICONS.get(t, "•")
            lines.append(f"| {icon} {t.capitalize()} | {count} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # High-impact events
    high_impact = [e for e in events if e.get("impact") in ("positive", "negative")]
    if high_impact:
        lines.append("## High-Impact Events")
        lines.append("")
        lines.append("| Date | Event | Ticker | Impact | Type |")
        lines.append("|------|-------|--------|--------|------|")
        for e in high_impact:
            impact_icon = IMPACT_ICONS.get(e.get("impact", ""), "⚪")
            type_icon = TYPE_ICONS.get(e.get("type", ""), "•")
            ticker = e.get("ticker") or "—"
            lines.append(
                f"| {e['date']} | {e['event']} | {ticker} | "
                f"{impact_icon} {e.get('impact', '')} | {type_icon} {e.get('type', '')} |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")

    # Weekly view
    lines.append("## Weekly Calendar")
    lines.append("")
    lines.append(generate_weekly_preview(data))
    lines.append("---")
    lines.append("")

    # Full event table
    lines.append("## All Events")
    lines.append("")
    lines.append("| Date | Event | Ticker | Type | Impact | Source |")
    lines.append("|------|-------|--------|------|--------|--------|")
    for e in events:
        impact_icon = IMPACT_ICONS.get(e.get("impact", ""), "⚪")
        type_icon = TYPE_ICONS.get(e.get("type", ""), "•")
        ticker = e.get("ticker") or "—"
        source = e.get("source", "")
        notes = e.get("notes", "")
        event_text = e["event"]
        if notes:
            event_text += f" *({notes[:50]}{'…' if len(notes) > 50 else ''})*"
        lines.append(
            f"| {e['date']} | {event_text} | {ticker} | "
            f"{type_icon} {e.get('type', '')} | {impact_icon} | {source} |"
        )
    lines.append("")

    # Action items
    today = date.today()
    next_week = today + timedelta(days=7)
    next_week_str = next_week.isoformat()
    today_str = today.isoformat()
    imminent = [
        e for e in events
        if e.get("date") and today_str <= e["date"] <= next_week_str
        and e.get("type") == "earnings"
    ]
    if imminent:
        lines.append("## Action Items")
        lines.append("")
        for e in imminent:
            ticker = e.get("ticker", "???")
            lines.append(
                f"- **{ticker}** earnings on {e['date']} — "
                f"run earnings-preview if not done"
            )
        lines.append("")

    lines.append(
        f"\n*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n"
    )

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate catalyst calendar report from collected data",
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="Generate weekly preview only (shorter output)",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Also upsert report to database via POST /api/analysis/reports",
    )
    args = parser.parse_args()

    data = io.read_json("calendar.json")
    if not data:
        print("  ✗  No calendar.json found. Run collect_catalysts.py first.", file=sys.stderr)
        sys.exit(1)

    print("\n  Generating calendar report…")

    if args.weekly:
        report_md = "# Catalyst Calendar — Weekly Preview\n\n"
        report_md += generate_weekly_preview(data)
    else:
        report_md = generate_full_report(data)

    path = io.write_text("calendar.md", report_md)
    print(f"  ✓  Wrote {path}")

    if args.persist:
        print("  Persisting to database…")
        with httpx.Client(base_url=API_URL) as client:
            try:
                resp = client.post(
                    "/api/analysis/reports",
                    json={
                        "ticker": "_PORTFOLIO",
                        "report_type": "catalyst_calendar",
                        "title": "Catalyst Calendar",
                        "content_md": report_md,
                        "file_path": str(path),
                        "generated_by": "catalyst-calendar",
                    },
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                print("  ✓  Persisted to database")
            except httpx.HTTPStatusError as exc:
                print(f"  ⚠  Failed to persist: {exc.response.status_code}", file=sys.stderr)
            except httpx.ConnectError:
                print("  ⚠  Cannot reach API — report saved locally only", file=sys.stderr)

    print()


if __name__ == "__main__":
    main()
