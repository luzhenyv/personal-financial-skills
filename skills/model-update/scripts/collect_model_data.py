#!/usr/bin/env python3
"""Collect current financials and existing projections for model update.

Usage:
    uv run python skills/model-update/scripts/collect_model_data.py TICKER
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Allow running from repo root without installing
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO, read_artifact_json  # noqa: E402

API_URL = os.getenv("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


def _get(path: str, params: dict | None = None) -> dict | list | None:
    try:
        r = httpx.get(f"{API_URL}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, Exception) as exc:
        print(f"  WARN: {path} → {exc}")
        return None


def collect(ticker: str) -> dict:
    ticker = ticker.upper()
    print(f"Collecting model data for {ticker} ...")

    data: dict = {"ticker": ticker}

    # Annual financials
    annual = _get(f"/api/financials/{ticker}/annual", {"years": 5})
    data["annual"] = annual or []
    print(f"  Annual periods: {len(data['annual'])}")

    # Quarterly financials
    quarterly = _get(f"/api/financials/{ticker}/quarterly", {"quarters": 8})
    data["quarterly"] = quarterly or []
    print(f"  Quarterly periods: {len(data['quarterly'])}")

    # Current metrics
    data["metrics"] = _get(f"/api/financials/{ticker}/metrics") or {}

    # Company info (for share count, market cap context)
    data["company"] = _get(f"/api/companies/{ticker}") or {}

    # Current prices (last 30 days for context)
    prices = _get(f"/api/financials/{ticker}/prices", {"period": "1m"})
    if prices:
        data["current_price"] = prices[-1].get("close") if prices else None
        data["price_30d_ago"] = prices[0].get("close") if prices else None
    else:
        data["current_price"] = None
        data["price_30d_ago"] = None

    # Existing projections (cross-skill read)
    existing = read_artifact_json(ticker, "model", "projections.json")
    data["existing_projections"] = existing

    # Thesis data (cross-skill read)
    thesis = read_artifact_json(ticker, "thesis", "thesis.json")
    data["thesis"] = thesis

    # Latest earnings analysis files
    earnings_io = ArtifactIO(ticker, "earnings")
    earnings_files = earnings_io.list_files("Q*_*_analysis.md")
    if earnings_files:
        latest = earnings_files[-1]
        data["latest_earnings_file"] = latest.name
        data["latest_earnings_summary"] = latest.read_text(encoding="utf-8")[:2000]
    else:
        data["latest_earnings_file"] = None
        data["latest_earnings_summary"] = None

    # Compute trailing metrics from quarterly data for convenience
    if data["quarterly"]:
        ttm = data["quarterly"][:4]  # most recent 4 quarters
        ttm_revenue = sum(q.get("revenue") or 0 for q in ttm)
        ttm_net_income = sum(q.get("net_income") or 0 for q in ttm)
        ttm_eps = sum(q.get("eps_diluted") or q.get("eps") or 0 for q in ttm)
        data["ttm"] = {
            "revenue": ttm_revenue,
            "net_income": ttm_net_income,
            "eps": ttm_eps,
        }
    else:
        data["ttm"] = {}

    # Write raw data
    io = ArtifactIO(ticker, "model")
    out = io.write_json("model_data_raw.json", data)
    print(f"  Written → {out}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect model data for ticker")
    parser.add_argument("ticker", help="Stock ticker (e.g. NVDA)")
    args = parser.parse_args()
    collect(args.ticker)


if __name__ == "__main__":
    main()
