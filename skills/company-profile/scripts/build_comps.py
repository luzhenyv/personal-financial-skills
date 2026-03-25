"""
Task 2: Build Comparable Company Analysis Table
================================================
Thin client that calls ``GET /api/analysis/comps/{TICKER}`` on the FastAPI server.
The server handles yfinance calls, caching, and TTL.

Falls back to direct yfinance calls if the API is unavailable.

Saves result to data/artifacts/{TICKER}/profile/comps_table.json.

Usage:
    uv run python skills/company-profile/scripts/build_comps.py NVDA
    uv run python skills/company-profile/scripts/build_comps.py AAPL --peers MSFT,GOOGL,META,AMZN
    uv run python skills/company-profile/scripts/build_comps.py NVDA --refresh
"""

import argparse
import json
import os
from pathlib import Path

import httpx

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")


def fetch_from_api(ticker: str, peers: str | None, refresh: bool) -> dict | None:
    """Call the comps API endpoint."""
    params: dict = {}
    if peers:
        params["peers"] = peers
    if refresh:
        params["refresh"] = "true"

    url = f"{API_URL}/api/analysis/comps/{ticker}"
    try:
        resp = httpx.get(url, params=params, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        print(f"API returned {resp.status_code}: {resp.text[:200]}")
    except httpx.HTTPError as e:
        print(f"API unavailable ({e}), falling back to direct yfinance calls...")
    return None


def fetch_direct(ticker: str, peers_csv: str | None) -> dict:
    """Fallback: call pfs.analysis.comps directly (requires yfinance)."""
    from pfs.analysis.comps import build_comps

    peers_list = [p.strip().upper() for p in peers_csv.split(",") if p.strip()] if peers_csv else None
    return build_comps(ticker, peers_override=peers_list, force_refresh=True)


def main():
    parser = argparse.ArgumentParser(description="Task 2: Build comps table")
    parser.add_argument("ticker", help="Subject company ticker, e.g. NVDA")
    parser.add_argument(
        "--peers",
        help="Comma-separated peer tickers to override auto-discovery",
        default="",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force refresh (ignore cache)",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    peers = args.peers if args.peers else None
    processed_dir = Path(f"data/artifacts/{ticker}/profile")
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Try API first, fall back to direct
    result = fetch_from_api(ticker, peers, args.refresh)
    if result is None:
        result = fetch_direct(ticker, peers)

    # Save
    out_path = processed_dir / "comps_table.json"
    out_path.write_text(json.dumps(result, indent=2))

    peer_count = len(result.get("peers", []))
    summary = result.get("peer_summary", {})
    gm = summary.get("gross_margin_pct", {})
    pe = summary.get("pe_forward", {})
    ev = summary.get("ev_ebitda", {})

    print(f"\nSaved {peer_count} companies → {out_path}")
    if isinstance(gm, dict):
        print(
            f"Peer median: gm={gm.get('median')}% | "
            f"pe_fwd={pe.get('median') if isinstance(pe, dict) else pe}x | "
            f"ev/ebitda={ev.get('median') if isinstance(ev, dict) else ev}x"
        )


if __name__ == "__main__":
    main()
