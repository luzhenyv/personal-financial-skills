"""Comparable company analysis engine.

Server-side comps computation: fetches peer data via yfinance, computes
statistics, caches results.  Exposed as ``GET /api/analysis/comps/{ticker}``
via the analysis router.
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _safe_round(val: Any, decimals: int = 1) -> float | None:
    try:
        v = float(val)
        return round(v, decimals) if v else None
    except (TypeError, ValueError):
        return None


def fetch_peer_data(ticker: str) -> dict[str, Any] | None:
    """Fetch market and financial metrics for a single ticker via yfinance."""
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        rev = info.get("totalRevenue") or 0
        gm = info.get("grossMargins")
        om = info.get("operatingMargins")
        rg = info.get("revenueGrowth")

        return {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName", ticker),
            "sector": info.get("sector", ""),
            "market_cap_b": _safe_round((info.get("marketCap") or 0) / 1e9),
            "revenue_ltm_b": _safe_round(rev / 1e9) if rev else None,
            "rev_growth_pct": _safe_round(rg * 100) if rg is not None else None,
            "gross_margin_pct": _safe_round(gm * 100) if gm is not None else None,
            "operating_margin_pct": _safe_round(om * 100) if om is not None else None,
            "net_margin_pct": _safe_round((info.get("profitMargins") or 0) * 100) or None,
            "pe_forward": _safe_round(info.get("forwardPE") or 0) or None,
            "pe_trailing": _safe_round(info.get("trailingPE") or 0) or None,
            "ev_ebitda": _safe_round(info.get("enterpriseToEbitda") or 0) or None,
            "ps_ratio": _safe_round(info.get("priceToSalesTrailing12Months") or 0, 2) or None,
            "pb_ratio": _safe_round(info.get("priceToBook") or 0, 2) or None,
            "beta": info.get("beta"),
            "dividend_yield_pct": _safe_round((info.get("dividendYield") or 0) * 100, 2) or None,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch peer data for {ticker}: {e}")
        return None


def discover_peers(ticker: str) -> list[str]:
    """Discover peer tickers from artifacts and yfinance fallback."""
    peers: list[str] = []

    # 1. Try curated competitive_landscape.json
    comps_path = Path("data/artifacts") / ticker / "profile" / "competitive_landscape.json"
    if comps_path.exists():
        try:
            data = json.loads(comps_path.read_text(encoding="utf-8"))
            for comp in data.get("competitors", []):
                t = comp.get("ticker", "")
                if t and len(t) <= 6 and t.replace(".", "").isalpha() and t.upper() not in ("N/A", "PRIVATE"):
                    peers.append(t.upper())
        except Exception:
            pass

    if peers:
        return peers

    # 2. Fallback to yfinance
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        yf_peers = info.get("recommendedSymbols", [])
        if yf_peers:
            peers = [p["symbol"] for p in yf_peers if isinstance(p, dict)][:8]
    except Exception:
        pass

    return peers


def compute_summary(rows: list[dict], exclude_ticker: str) -> dict[str, Any]:
    """Compute median, mean, min, max for key metrics across peers."""
    peer_rows = [r for r in rows if r["ticker"] != exclude_ticker]

    def stats(key: str) -> dict:
        vals = [r[key] for r in peer_rows if r.get(key) is not None]
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


# ── Cache ──────────────────────────────────────────────────────────────────────

_CACHE_TTL_HOURS = 4


def _get_cached(cache_path: Path) -> dict | None:
    """Return cached comps if fresh enough."""
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        gen_date = data.get("generated_date", "")
        if gen_date == date.today().isoformat():
            return data
    except Exception:
        pass
    return None


def _save_cache(cache_path: Path, data: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ── Public API ─────────────────────────────────────────────────────────────────

def build_comps(
    ticker: str,
    peers_override: list[str] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Build a comparable company analysis table.

    Returns a dict matching the ``comps_table.json`` schema.
    Results are cached under ``data/artifacts/{ticker}/profile/comps_table.json``
    with a same-day TTL.
    """
    ticker = ticker.upper()
    cache_path = Path("data/artifacts") / ticker / "profile" / "comps_table.json"

    if not force_refresh:
        cached = _get_cached(cache_path)
        if cached:
            logger.info(f"[{ticker}] Returning cached comps")
            return cached

    # Determine peer list
    if peers_override:
        peers = [p.upper() for p in peers_override]
    else:
        peers = discover_peers(ticker)

    # Subject ticker always included
    all_tickers = list(dict.fromkeys(peers))
    if ticker not in all_tickers:
        all_tickers.append(ticker)

    # Fetch data for all
    rows: list[dict] = []
    for t in all_tickers:
        row = fetch_peer_data(t)
        if row:
            rows.append(row)

    summary = compute_summary(rows, ticker)

    result = {
        "ticker": ticker,
        "generated_date": date.today().isoformat(),
        "peers": rows,
        "peer_summary": summary,
    }

    _save_cache(cache_path, result)
    return result
