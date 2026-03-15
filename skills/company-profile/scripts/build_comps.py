"""
Task 2: Build Comparable Company Analysis Table
================================================
Fetches market data for the subject company and its peers from Yahoo Finance,
builds a standardized comps table, and saves it to data/artifacts/{TICKER}/profile/comps_table.json.

Peer discovery priority:
  1. Tickers listed in data/artifacts/{TICKER}/profile/competitive_landscape.json (curated by Task 1)
  2. Fallback: yfinance recommended peers for the ticker

Usage:
    uv run python skills/company-profile/scripts/build_comps.py NVDA
    uv run python skills/company-profile/scripts/build_comps.py AAPL --peers MSFT,GOOGL,META,AMZN
"""

import argparse
import json
import statistics
from pathlib import Path

import yfinance as yf


def fetch_peer_data(ticker: str) -> dict:
    """Fetch key market and financial metrics for a single ticker via yfinance."""
    info = yf.Ticker(ticker).info
    rev = info.get("totalRevenue") or 0
    gm = info.get("grossMargins")
    om = info.get("operatingMargins")
    rg = info.get("revenueGrowth")
    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName", ticker),
        "sector": info.get("sector", ""),
        "market_cap_b": round((info.get("marketCap") or 0) / 1e9, 1),
        "revenue_ltm_b": round(rev / 1e9, 1) if rev else None,
        "rev_growth_pct": round(rg * 100, 1) if rg is not None else None,
        "gross_margin_pct": round(gm * 100, 1) if gm is not None else None,
        "operating_margin_pct": round(om * 100, 1) if om is not None else None,
        "net_margin_pct": round((info.get("profitMargins") or 0) * 100, 1) or None,
        "pe_forward": round(info.get("forwardPE") or 0, 1) or None,
        "pe_trailing": round(info.get("trailingPE") or 0, 1) or None,
        "ev_ebitda": round(info.get("enterpriseToEbitda") or 0, 1) or None,
        "ps_ratio": round(info.get("priceToSalesTrailing12Months") or 0, 2) or None,
        "pb_ratio": round(info.get("priceToBook") or 0, 2) or None,
        "beta": info.get("beta"),
        "dividend_yield_pct": round((info.get("dividendYield") or 0) * 100, 2) or None,
    }


def get_peers_from_processed(ticker: str) -> list[str]:
    """Extract peer tickers from the curated competitive_landscape.json (Task 1 output)."""
    path = Path(f"data/artifacts/{ticker}/profile/competitive_landscape.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    tickers = []
    for comp in data.get("competitors", []):
        t = comp.get("ticker", "")
        # Filter out non-public / internal tickers
        if t and len(t) <= 6 and t.isalpha() and t.upper() not in ("N/A", "PRIVATE"):
            tickers.append(t.upper())
    return tickers


def get_peers_from_yfinance(ticker: str) -> list[str]:
    """Use yfinance's recommendedSymbols as fallback peer list."""
    try:
        recs = yf.Ticker(ticker).recommendations
        if recs is None or recs.empty:
            return []
        # yf.Ticker.recommendations returns analyst upgrades/downgrades, not peers
        # Use info.get("recommendedSymbols") if available
        info = yf.Ticker(ticker).info
        peers = info.get("recommendedSymbols", [])
        return [p["symbol"] for p in (peers or []) if isinstance(p, dict)][:8]
    except Exception:
        return []


def compute_summary(rows: list[dict], exclude_ticker: str) -> dict:
    """Compute median, mean, min, max for key metrics across peers (excluding subject)."""
    peers = [r for r in rows if r["ticker"] != exclude_ticker]

    def stats(key):
        vals = [r[key] for r in peers if r.get(key) is not None]
        if not vals:
            return {"median": None, "mean": None, "min": None, "max": None}
        return {
            "median": round(statistics.median(vals), 1),
            "mean": round(statistics.mean(vals), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
        }

    return {
        "ticker": "PEER_SUMMARY",
        "name": "Peer Summary",
        "market_cap_b": stats("market_cap_b"),
        "revenue_ltm_b": stats("revenue_ltm_b"),
        "rev_growth_pct": stats("rev_growth_pct"),
        "gross_margin_pct": stats("gross_margin_pct"),
        "operating_margin_pct": stats("operating_margin_pct"),
        "pe_forward": stats("pe_forward"),
        "ev_ebitda": stats("ev_ebitda"),
        "ps_ratio": stats("ps_ratio"),
    }


def main():
    parser = argparse.ArgumentParser(description="Task 2: Build comps table")
    parser.add_argument("ticker", help="Subject company ticker, e.g. NVDA")
    parser.add_argument(
        "--peers",
        help="Comma-separated peer tickers to override auto-discovery, e.g. AMD,INTC,AVGO",
        default="",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    processed_dir = Path(f"data/artifacts/{ticker}/profile")
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ── Determine peer list ────────────────────────────────────────────────────
    if args.peers:
        peers = [p.strip().upper() for p in args.peers.split(",") if p.strip()]
        print(f"Using user-supplied peers: {peers}")
    else:
        peers = get_peers_from_processed(ticker)
        if peers:
            print(f"Using peers from competitive_landscape.json: {peers}")
        else:
            peers = get_peers_from_yfinance(ticker)
            print(f"Using yfinance fallback peers: {peers}")

    if not peers:
        print(f"Warning: No peers found for {ticker}. Will build single-row table.")

    # Subject ticker always included, deduplicated, subject first at end
    all_tickers = list(dict.fromkeys(peers))  # preserve order, deduplicate
    if ticker not in all_tickers:
        all_tickers.append(ticker)

    # ── Fetch data ─────────────────────────────────────────────────────────────
    rows = []
    for t in all_tickers:
        print(f"  Fetching {t} ...", end=" ", flush=True)
        try:
            row = fetch_peer_data(t)
            rows.append(row)
            print(
                f"cap=${row['market_cap_b']:.0f}B "
                f"rev=${row['revenue_ltm_b']}B "
                f"gm={row['gross_margin_pct']}% "
                f"pe_fwd={row['pe_forward']}"
            )
        except Exception as e:
            print(f"ERROR: {e}")

    # ── Compute summary stats ──────────────────────────────────────────────────
    summary = compute_summary(rows, ticker)

    # ── Save ──────────────────────────────────────────────────────────────────
    out = {
        "ticker": ticker,
        "generated_date": __import__("datetime").date.today().isoformat(),
        "peers": rows,
        "peer_summary": summary,
    }
    out_path = processed_dir / "comps_table.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved {len(rows)} companies → {out_path}")
    print(f"Peer median: gm={summary['gross_margin_pct']['median']}% | "
          f"pe_fwd={summary['pe_forward']['median']}x | "
          f"ev/ebitda={summary['ev_ebitda']['median']}x")


if __name__ == "__main__":
    main()
