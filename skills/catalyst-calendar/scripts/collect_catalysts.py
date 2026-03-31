#!/usr/bin/env python3
"""Catalyst Calendar — Collect and Aggregate Catalysts.

Scans all ticker thesis artifacts for pending catalysts, merges with
macro events and SEC filing dates into a unified calendar.

Usage::

    uv run python skills/catalyst-calendar/scripts/collect_catalysts.py
    uv run python skills/catalyst-calendar/scripts/collect_catalysts.py --days 30
    uv run python skills/catalyst-calendar/scripts/collect_catalysts.py --upcoming 14
    uv run python skills/catalyst-calendar/scripts/collect_catalysts.py --add-macro \
        --event "FOMC Rate Decision" --date 2026-05-07 --impact neutral
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

# ── Path setup ───────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ARTIFACTS_ROOT, ArtifactIO, read_artifact_json

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30

io = ArtifactIO("_portfolio", "catalysts")


# ── API helper ───────────────────────────────────────────────


def _get(client: httpx.Client, path: str, **params: object) -> dict | list | None:
    """GET helper — returns parsed JSON or None on error."""
    try:
        resp = client.get(path, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        print(f"  ⚠  {path} → {exc.response.status_code}", file=sys.stderr)
        return None
    except httpx.ConnectError:
        print(f"  ⚠  Cannot reach API at {client.base_url}", file=sys.stderr)
        return None


# ── Default macro events for 2026 ───────────────────────────
# Pre-populated with known scheduled dates. Users can extend via --add-macro.

DEFAULT_MACRO_EVENTS: list[dict] = [
    # FOMC meetings 2026 (approximate dates)
    {"date": "2026-01-28", "event": "FOMC Rate Decision (Jan)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-03-18", "event": "FOMC Rate Decision (Mar)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-05-06", "event": "FOMC Rate Decision (May)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-06-17", "event": "FOMC Rate Decision (Jun)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-07-29", "event": "FOMC Rate Decision (Jul)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-09-16", "event": "FOMC Rate Decision (Sep)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-11-04", "event": "FOMC Rate Decision (Nov)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-12-16", "event": "FOMC Rate Decision (Dec)", "type": "macro", "impact": "neutral", "notes": ""},
    # CPI releases 2026 (approximate — usually 2nd or 3rd week)
    {"date": "2026-01-14", "event": "CPI Report (Dec 2025)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-02-11", "event": "CPI Report (Jan)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-03-11", "event": "CPI Report (Feb)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-04-14", "event": "CPI Report (Mar)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-05-12", "event": "CPI Report (Apr)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-06-10", "event": "CPI Report (May)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-07-14", "event": "CPI Report (Jun)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-08-12", "event": "CPI Report (Jul)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-09-15", "event": "CPI Report (Aug)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-10-13", "event": "CPI Report (Sep)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-11-12", "event": "CPI Report (Oct)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-12-10", "event": "CPI Report (Nov)", "type": "macro", "impact": "neutral", "notes": ""},
    # Jobs reports 2026 (first Friday of each month)
    {"date": "2026-01-09", "event": "Jobs Report (Dec 2025)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-02-06", "event": "Jobs Report (Jan)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-03-06", "event": "Jobs Report (Feb)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-04-03", "event": "Jobs Report (Mar)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-05-08", "event": "Jobs Report (Apr)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-06-05", "event": "Jobs Report (May)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-07-02", "event": "Jobs Report (Jun)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-08-07", "event": "Jobs Report (Jul)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-09-04", "event": "Jobs Report (Aug)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-10-02", "event": "Jobs Report (Sep)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-11-06", "event": "Jobs Report (Oct)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-12-04", "event": "Jobs Report (Nov)", "type": "macro", "impact": "neutral", "notes": ""},
    # GDP reports 2026 (end of month, quarterly)
    {"date": "2026-01-29", "event": "GDP Q4 2025 (Advance)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-04-29", "event": "GDP Q1 2026 (Advance)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-07-29", "event": "GDP Q2 2026 (Advance)", "type": "macro", "impact": "neutral", "notes": ""},
    {"date": "2026-10-29", "event": "GDP Q3 2026 (Advance)", "type": "macro", "impact": "neutral", "notes": ""},
]


# ── Catalyst collection ──────────────────────────────────────


def _parse_date(date_str: str | None) -> str | None:
    """Normalize date strings. Handles YYYY-MM-DD and YYYY-QN formats."""
    if not date_str:
        return None
    # Already standard format
    if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
        return date_str
    # Quarter format: YYYY-Q1 → YYYY-03-31 (end of quarter)
    if "Q" in date_str.upper():
        parts = date_str.upper().replace("Q", "-Q").split("-Q")
        if len(parts) == 2:
            year = parts[0].strip("-")
            quarter = int(parts[1])
            quarter_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
            return f"{year}-{quarter_end.get(quarter, '12-31')}"
    return date_str


def _collect_thesis_catalysts() -> list[dict]:
    """Scan all ticker artifacts for pending catalysts."""
    events: list[dict] = []

    if not ARTIFACTS_ROOT.exists():
        return events

    for ticker_dir in sorted(ARTIFACTS_ROOT.iterdir()):
        # Skip special directories
        if not ticker_dir.is_dir() or ticker_dir.name.startswith("_"):
            continue

        ticker = ticker_dir.name
        catalysts_file = ticker_dir / "thesis" / "catalysts.json"
        if not catalysts_file.exists():
            continue

        try:
            with catalysts_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            print(f"  ⚠  Could not read {catalysts_file}", file=sys.stderr)
            continue

        # Handle both "catalysts" and "entries" keys (schema variations)
        catalyst_list = data.get("catalysts") or data.get("entries") or []

        for cat in catalyst_list:
            status = cat.get("status", "pending")
            if status in ("resolved", "expired"):
                continue  # Only include pending/postponed

            event_date = _parse_date(cat.get("expected_date") or cat.get("date"))

            # Classify event type from the event text
            event_text = cat.get("event", "")
            event_type = _classify_event(event_text)

            events.append({
                "date": event_date,
                "event": event_text,
                "ticker": ticker,
                "type": event_type,
                "impact": cat.get("expected_impact") or cat.get("impact", "neutral"),
                "source": "thesis-tracker",
                "affected_assumptions": cat.get("affected_assumptions"),
                "notes": cat.get("notes", ""),
                "status": status,
            })

    return events


def _classify_event(event_text: str) -> str:
    """Classify event type from its description."""
    lower = event_text.lower()
    if any(kw in lower for kw in ("earnings", "q1 ", "q2 ", "q3 ", "q4 ", "quarterly", "fiscal")):
        return "earnings"
    if any(kw in lower for kw in ("fda", "regulatory", "antitrust", "export control", "tariff")):
        return "regulatory"
    if any(kw in lower for kw in ("conference", "investor day", "analyst day", "gtc", "summit")):
        return "conference"
    if any(kw in lower for kw in ("launch", "release", "announcement", "product")):
        return "corporate"
    if any(kw in lower for kw in ("fomc", "cpi", "gdp", "jobs", "fed", "pce", "inflation")):
        return "macro"
    return "corporate"


def _collect_filing_dates(client: httpx.Client, tickers: list[str]) -> list[dict]:
    """Fetch recent/upcoming SEC filing dates from the API."""
    events: list[dict] = []
    today = date.today()

    for ticker in tickers:
        filings = _get(client, f"/api/filings/{ticker}/")
        if not filings:
            continue

        for f in filings:
            filing_date_str = f.get("filing_date")
            if not filing_date_str:
                continue

            try:
                filing_date = date.fromisoformat(filing_date_str)
            except ValueError:
                continue

            # Only include recent filings (last 30 days) or future ones
            if filing_date < today - timedelta(days=30):
                continue

            filing_type = f.get("filing_type", "")
            if filing_type not in ("10-K", "10-Q", "8-K"):
                continue

            events.append({
                "date": filing_date_str,
                "event": f"{filing_type} Filing — {ticker}",
                "ticker": ticker,
                "type": "filing",
                "impact": "neutral",
                "source": "sec_filings",
                "affected_assumptions": None,
                "notes": f"Accession: {f.get('accession_number', '')}",
                "status": "resolved" if filing_date <= today else "pending",
            })

    return events


def _load_macro_events() -> list[dict]:
    """Load macro events from artifact or initialize with defaults."""
    data = io.read_json("macro_events.json")
    if data and "events" in data:
        return data["events"]
    # Initialize with defaults
    _save_macro_events(DEFAULT_MACRO_EVENTS)
    return list(DEFAULT_MACRO_EVENTS)


def _save_macro_events(events: list[dict]) -> None:
    """Persist macro events to artifact."""
    io.write_json("macro_events.json", {"events": events})


def _add_macro_event(event: str, event_date: str, impact: str, notes: str) -> None:
    """Add a macro event to the persistent calendar."""
    events = _load_macro_events()

    # Check for duplicates
    for e in events:
        if e["date"] == event_date and e["event"] == event:
            print(f"  ⚠  Event already exists: {event} on {event_date}")
            return

    events.append({
        "date": event_date,
        "event": event,
        "type": "macro",
        "impact": impact,
        "notes": notes,
    })
    events.sort(key=lambda x: x.get("date", ""))
    _save_macro_events(events)
    print(f"  ✓  Added macro event: {event} on {event_date}")


def _macro_to_calendar_events(macro_events: list[dict]) -> list[dict]:
    """Convert macro events to unified calendar event format."""
    result = []
    for m in macro_events:
        result.append({
            "date": m["date"],
            "event": m["event"],
            "ticker": None,
            "type": "macro",
            "impact": m.get("impact", "neutral"),
            "source": "macro_calendar",
            "affected_assumptions": None,
            "notes": m.get("notes", ""),
            "status": "pending",
        })
    return result


# ── Calendar assembly ────────────────────────────────────────


def _iso_week(date_str: str) -> str:
    """Convert a date string to ISO week format (YYYY-Www)."""
    try:
        d = date.fromisoformat(date_str)
        iso_cal = d.isocalendar()
        return f"{iso_cal.year}-W{iso_cal.week:02d}"
    except (ValueError, TypeError):
        return "unknown"


def collect_calendar(horizon_days: int = 90) -> dict:
    """Collect all catalysts and build unified calendar.

    Returns the calendar dict ready for artifact storage.
    """
    today = date.today()
    horizon_end = today + timedelta(days=horizon_days)
    today_str = today.isoformat()
    end_str = horizon_end.isoformat()

    print(f"\n{'='*60}")
    print(f"  Catalyst Calendar — Collecting Events")
    print(f"  Horizon: {today_str} → {end_str} ({horizon_days} days)")
    print(f"{'='*60}\n")

    # 1. Thesis-tracker catalysts
    print("  Scanning thesis artifacts…")
    thesis_events = _collect_thesis_catalysts()
    print(f"  Found {len(thesis_events)} thesis catalysts")

    # 2. SEC filing dates
    tickers = [e["ticker"] for e in thesis_events if e.get("ticker")]
    tickers = sorted(set(tickers))

    filing_events: list[dict] = []
    with httpx.Client(base_url=API_URL) as client:
        # Also try to get portfolio tickers
        positions = _get(client, "/api/portfolio/positions")
        if positions and isinstance(positions, list):
            for p in positions:
                t = p.get("ticker")
                if t and t not in tickers:
                    tickers.append(t)

        # Also check all companies if no positions
        if not tickers:
            companies = _get(client, "/api/companies/")
            if companies:
                tickers = [c["ticker"] for c in companies]

        if tickers:
            print(f"  Fetching filing dates for {len(tickers)} tickers…")
            filing_events = _collect_filing_dates(client, tickers)
            print(f"  Found {len(filing_events)} filing events")

    # 3. Macro events
    print("  Loading macro calendar…")
    macro_events = _load_macro_events()
    macro_calendar_events = _macro_to_calendar_events(macro_events)
    print(f"  Loaded {len(macro_calendar_events)} macro events")

    # 4. Merge all events
    all_events = thesis_events + filing_events + macro_calendar_events

    # Filter to horizon window
    filtered: list[dict] = []
    for e in all_events:
        d = e.get("date")
        if not d:
            continue
        if today_str <= d <= end_str:
            filtered.append(e)

    # Sort by date
    filtered.sort(key=lambda x: (x.get("date", ""), x.get("ticker") or "", x.get("event", "")))

    # Build by_week grouping
    by_week: dict[str, list[dict]] = {}
    for e in filtered:
        week = _iso_week(e["date"])
        by_week.setdefault(week, []).append({
            "date": e["date"],
            "event": e["event"],
            "ticker": e.get("ticker"),
            "type": e["type"],
        })

    # Build by_type counts
    by_type: dict[str, int] = {}
    for e in filtered:
        t = e.get("type", "other")
        by_type[t] = by_type.get(t, 0) + 1

    calendar = {
        "horizon_start": today_str,
        "horizon_end": end_str,
        "total_events": len(filtered),
        "events": filtered,
        "by_week": dict(sorted(by_week.items())),
        "by_type": by_type,
    }

    print(f"\n  {'─'*40}")
    print(f"  Calendar assembled: {len(filtered)} events in {len(by_week)} weeks")
    for t, count in sorted(by_type.items()):
        print(f"    {t:15s} {count:3d}")

    return calendar


def show_upcoming(days: int = 14) -> None:
    """Display upcoming events from the existing calendar."""
    data = io.read_json("calendar.json")
    if not data:
        print("  ✗  No calendar.json found. Run collect first.", file=sys.stderr)
        sys.exit(1)

    today = date.today()
    cutoff = (today + timedelta(days=days)).isoformat()
    today_str = today.isoformat()

    events = [
        e for e in data.get("events", [])
        if e.get("date") and today_str <= e["date"] <= cutoff
    ]

    if not events:
        print(f"\n  No events in the next {days} days.\n")
        return

    print(f"\n  Upcoming Events (next {days} days)")
    print(f"  {'─'*50}")

    current_week = ""
    for e in events:
        week = _iso_week(e["date"])
        if week != current_week:
            current_week = week
            print(f"\n  Week {week}:")

        ticker_str = f" [{e['ticker']}]" if e.get("ticker") else ""
        impact_icon = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(
            e.get("impact", "neutral"), "⚪"
        )
        print(f"    {e['date']}  {impact_icon} {e['event']}{ticker_str}  ({e['type']})")

    print()


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Catalyst Calendar — Collect and Aggregate Catalysts",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Horizon in days (default: 90)",
    )
    parser.add_argument(
        "--upcoming",
        type=int,
        default=None,
        metavar="DAYS",
        help="Show upcoming events for next N days (from existing calendar)",
    )
    parser.add_argument(
        "--add-macro",
        action="store_true",
        help="Add a macro event instead of collecting",
    )
    parser.add_argument("--event", type=str, help="Event description (for --add-macro)")
    parser.add_argument("--date", type=str, help="Event date YYYY-MM-DD (for --add-macro)")
    parser.add_argument(
        "--impact",
        type=str,
        default="neutral",
        choices=["positive", "negative", "neutral"],
        help="Expected impact (for --add-macro)",
    )
    parser.add_argument("--notes", type=str, default="", help="Optional notes")

    args = parser.parse_args()

    # Mode: add macro event
    if args.add_macro:
        if not args.event or not args.date:
            print("  ✗  --add-macro requires --event and --date", file=sys.stderr)
            sys.exit(1)
        _add_macro_event(args.event, args.date, args.impact, args.notes)
        return

    # Mode: show upcoming
    if args.upcoming is not None:
        show_upcoming(args.upcoming)
        return

    # Mode: collect and build calendar
    calendar = collect_calendar(horizon_days=args.days)

    path = io.write_json("calendar.json", calendar)
    print(f"\n  ✓  Wrote {path}\n")


if __name__ == "__main__":
    main()
