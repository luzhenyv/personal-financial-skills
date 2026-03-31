#!/usr/bin/env python3
"""Task 1 — Collect morning briefing data from REST API + artifacts.

Gathers portfolio positions, P&L, recent price moves, catalyst calendar,
risk alerts, and thesis health into a single daily snapshot.

Usage::

    uv run python skills/morning-briefing/scripts/collect_briefing.py
    uv run python skills/morning-briefing/scripts/collect_briefing.py --date 2026-03-28
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO, read_artifact_json

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


def _get(path: str, params: dict | None = None) -> dict | list | None:
    url = f"{API_URL}{path}"
    try:
        resp = httpx.get(url, params=params or {}, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        print(f"  ⚠  {path} → {resp.status_code}")
    except httpx.HTTPError as e:
        print(f"  ✗  {path} failed: {e}")
    return None


def collect(briefing_date: date) -> bool:
    """Collect all data for the morning briefing."""
    date_str = briefing_date.isoformat()
    print(f"Collecting morning briefing data for {date_str}...")

    # Portfolio summary
    summary = _get("/api/portfolio/", {"portfolio_id": 1})
    if not summary:
        print("  ✗  Could not fetch portfolio. Is the API running?")
        return False

    positions = _get("/api/portfolio/positions", {"portfolio_id": 1}) or []
    print(f"  ✓  {len(positions)} positions")

    # Recent prices for each position (5 days for week context)
    position_prices = {}
    for pos in positions:
        ticker = pos.get("ticker", "")
        if ticker:
            prices = _get(f"/api/financials/{ticker}/prices", {"period": "5d"}) or []
            if prices:
                position_prices[ticker] = prices

    # Notable movers (>2% daily change)
    movers = []
    for pos in positions:
        pnl_pct = pos.get("unrealized_pnl_pct", 0)
        ticker = pos.get("ticker", "")
        prices = position_prices.get(ticker, [])
        daily_change = None
        if len(prices) >= 2:
            prev = prices[-2].get("close") or prices[-2].get("close_price")
            curr = prices[-1].get("close") or prices[-1].get("close_price")
            if prev and curr and prev != 0:
                daily_change = (curr - prev) / prev
        if daily_change and abs(daily_change) > 0.02:
            movers.append({
                "ticker": ticker,
                "daily_change_pct": round(daily_change, 4),
                "weight": pos.get("weight", 0),
                "market_value": pos.get("market_value", 0),
            })
    movers.sort(key=lambda x: abs(x.get("daily_change_pct", 0)), reverse=True)

    # Catalyst calendar — collect from all positions
    upcoming_catalysts = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        catalysts = read_artifact_json(ticker, "thesis", "catalysts.json")
        if catalysts and catalysts.get("entries"):
            for c in catalysts["entries"]:
                cat_date = c.get("date", "")
                resolved = c.get("resolved", False)
                if not resolved and cat_date >= date_str:
                    upcoming_catalysts.append({**c, "ticker": ticker})
    upcoming_catalysts.sort(key=lambda x: x.get("date", ""))

    # Risk alerts (recent)
    risk_alerts = read_artifact_json("_portfolio", "risk", "alerts.json")
    recent_alerts = []
    if risk_alerts and risk_alerts.get("entries"):
        # Last 5 alerts
        recent_alerts = risk_alerts["entries"][-5:]

    # Thesis health summary
    thesis_summary = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        health = read_artifact_json(ticker, "thesis", "health_checks.json")
        thesis_data = read_artifact_json(ticker, "thesis", "thesis.json")
        latest_score = None
        if health and health.get("entries"):
            latest_score = health["entries"][-1].get("composite_score")
        thesis_summary.append({
            "ticker": ticker,
            "has_thesis": thesis_data is not None,
            "health_score": latest_score,
            "weight": pos.get("weight", 0),
        })

    # Action items
    actions = []
    for ts in thesis_summary:
        if not ts["has_thesis"]:
            actions.append(f"Create thesis for {ts['ticker']} (weight: {ts['weight']:.1f}%)")
        elif ts["health_score"] is not None and ts["health_score"] < 40:
            actions.append(f"Review {ts['ticker']} — health score {ts['health_score']:.0f} (critical)")
        elif ts["health_score"] is None:
            actions.append(f"Run health check for {ts['ticker']} (no score on file)")

    # Assemble
    raw = {
        "date": date_str,
        "portfolio_summary": summary,
        "positions": positions,
        "notable_movers": movers,
        "upcoming_catalysts": upcoming_catalysts[:10],
        "recent_risk_alerts": recent_alerts,
        "thesis_summary": thesis_summary,
        "action_items": actions,
    }

    io = ArtifactIO("_daily", "briefings")
    path = io.write_json(f"{date_str}_raw.json", raw)
    print(f"\n✓  Raw data written to {path}")
    print(f"   Next: generate briefing markdown")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect morning briefing data")
    parser.add_argument("--date", help="Briefing date (YYYY-MM-DD, default: today)")
    args = parser.parse_args()

    d = date.fromisoformat(args.date) if args.date else date.today()
    success = collect(d)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
