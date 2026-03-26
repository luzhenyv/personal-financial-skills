#!/usr/bin/env python3
"""Task 1 — Collect portfolio data from Mini PORT API + thesis artifacts.

Calls the portfolio REST API endpoints and reads thesis artifacts for each
position, assembling a single ``portfolio_snapshot.json`` for the AI review
task.

Usage::

    uv run python skills/portfolio-analyst/scripts/collect_portfolio.py
    uv run python skills/portfolio-analyst/scripts/collect_portfolio.py --portfolio-id 2
    uv run python skills/portfolio-analyst/scripts/collect_portfolio.py --api-url http://remote:8000
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO, read_artifact_json

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


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
        print(f"  ✗  Cannot reach API at {client.base_url}", file=sys.stderr)
        sys.exit(1)


def collect(portfolio_id: int = 1, api_url: str = API_URL) -> dict:
    """Collect all portfolio + thesis data into a single snapshot dict."""
    params = {"portfolio_id": portfolio_id}

    with httpx.Client(base_url=api_url) as client:
        # ── Portfolio API calls ──────────────────────────────────────
        print("Collecting portfolio data from API...")

        summary = _get(client, "/api/portfolio/", **params)
        if summary is None:
            print("  ✗  Could not fetch portfolio summary. Is the API running?", file=sys.stderr)
            sys.exit(1)

        if summary.get("position_count", 0) == 0:
            print("  ⚠  Portfolio has no positions — nothing to analyze.", file=sys.stderr)
            # Still write the snapshot so the state is recorded
            return {
                "portfolio_id": portfolio_id,
                "summary": summary,
                "positions": [],
                "allocation": {},
                "performance": {},
                "pnl": {},
                "thesis_data": {},
            }

        positions = _get(client, "/api/portfolio/positions", **params) or []
        allocation = _get(client, "/api/portfolio/allocation", **params) or {}
        performance = _get(client, "/api/portfolio/performance", period="ytd", **params) or {}
        pnl = _get(client, "/api/portfolio/pnl", **params) or {}

        print(f"  ✓  {len(positions)} positions, cash ${summary.get('cash', 0):,.2f}")

        # ── Thesis artifacts for each position ───────────────────────
        print("Reading thesis artifacts...")
        thesis_data: dict[str, dict] = {}

        for pos in positions:
            ticker = pos.get("ticker", "")
            if not ticker:
                continue

            thesis = read_artifact_json(ticker, "thesis", "thesis.json")
            health_checks = read_artifact_json(ticker, "thesis", "health_checks.json")

            # Extract latest health check if available
            latest_health = None
            if health_checks and health_checks.get("entries"):
                latest_health = health_checks["entries"][-1]

            if thesis or latest_health:
                thesis_data[ticker] = {
                    "has_thesis": thesis is not None,
                    "thesis_statement": thesis.get("thesis", "") if thesis else None,
                    "conviction": thesis.get("conviction", "unset") if thesis else "unset",
                    "position_type": thesis.get("position", "long") if thesis else "long",
                    "sell_conditions": thesis.get("sell_conditions", []) if thesis else [],
                    "key_risks": thesis.get("key_risks", []) if thesis else [],
                    "latest_health_score": latest_health.get("composite_score") if latest_health else None,
                    "latest_health_recommendation": latest_health.get("recommendation") if latest_health else None,
                    "latest_health_date": latest_health.get("date") if latest_health else None,
                }
                status = "thesis ✓" if thesis else "no thesis"
                score = f", score={latest_health['composite_score']}" if latest_health else ""
                print(f"  {ticker}: {status}{score}")
            else:
                thesis_data[ticker] = {
                    "has_thesis": False,
                    "thesis_statement": None,
                    "conviction": "unset",
                    "position_type": "long",
                    "sell_conditions": [],
                    "key_risks": [],
                    "latest_health_score": None,
                    "latest_health_recommendation": None,
                    "latest_health_date": None,
                }
                print(f"  {ticker}: no thesis, no health data")

    return {
        "portfolio_id": portfolio_id,
        "summary": summary,
        "positions": positions,
        "allocation": allocation,
        "performance": performance,
        "pnl": pnl,
        "thesis_data": thesis_data,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect portfolio data for AI review")
    parser.add_argument("--portfolio-id", type=int, default=1, help="Portfolio ID (default: 1)")
    parser.add_argument("--api-url", default=API_URL, help=f"API base URL (default: {API_URL})")
    args = parser.parse_args()

    snapshot = collect(portfolio_id=args.portfolio_id, api_url=args.api_url)

    io = ArtifactIO("_portfolio", "analysis")
    path = io.write_json("portfolio_snapshot.json", snapshot)
    print(f"\n✓  Snapshot written to {path}")
    print("   Next: run the AI portfolio review (Task 2)")


if __name__ == "__main__":
    main()
