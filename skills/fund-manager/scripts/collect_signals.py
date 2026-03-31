#!/usr/bin/env python3
"""Task 1 — Collect signals from all skill artifacts + REST API.

Gathers cross-skill signals for every portfolio position:
  - Market signals (price momentum, technicals) ← REST API /signals/
  - Fundamental signals (margins, growth, valuation) ← REST API /signals/
  - Thesis signals (health score, assumption status) ← thesis artifacts
  - Risk signals (beta, VaR, drawdown, alerts) ← risk artifacts + API
  - Earnings signals (recent results, surprises) ← earnings artifacts
  - Catalyst signals (upcoming events) ← catalyst artifacts

Inspired by TradingAgents' 4 analyst roles (Market, Fundamentals,
News, Social Media) but adapted to PFS's artifact-first architecture.

Usage::

    uv run python skills/fund-manager/scripts/collect_signals.py
    uv run python skills/fund-manager/scripts/collect_signals.py --date 2026-03-31
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


def _post(path: str, params: dict | None = None) -> dict | list | None:
    url = f"{API_URL}{path}"
    try:
        resp = httpx.post(url, params=params or {}, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        print(f"  ⚠  POST {path} → {resp.status_code}")
    except httpx.HTTPError as e:
        print(f"  ✗  POST {path} failed: {e}")
    return None


# ── Signal collectors (one per "analyst") ────────────────────


def _collect_market_signals(ticker: str) -> dict:
    """Market + momentum + technical signals from REST API (≈ TradingAgents Market Analyst).

    Fetches full technical indicator suite: SMA(50,200), EMA(10),
    MACD/Signal/Histogram, RSI(14), Bollinger Bands, ATR(14), VWMA(20).
    """
    data = _get(f"/api/analysis/signals/{ticker}", {"lookback_days": 60})
    if not data:
        return {"source": "market", "status": "unavailable"}
    return {
        "source": "market",
        "status": "ok",
        "latest_price": data.get("latest_price"),
        "technicals": data.get("technicals", {}),
        "momentum": data.get("momentum", {}),
        "volatility": data.get("volatility", {}),
        "risk_metrics": data.get("risk", {}),
    }


def _collect_fundamental_signals(ticker: str) -> dict:
    """Fundamental signals from REST API (≈ TradingAgents Fundamentals Analyst)."""
    data = _get(f"/api/analysis/signals/{ticker}")
    metrics = data.get("fundamentals", {}) if data else {}

    # Also fetch recent income statement for growth context
    income = _get(f"/api/financials/{ticker}/income-statements", {"years": 2})
    growth_context = {}
    if income and len(income) >= 2:
        latest = income[0]
        prior = income[1]
        rev_latest = latest.get("total_revenue") or latest.get("revenue")
        rev_prior = prior.get("total_revenue") or prior.get("revenue")
        if rev_latest and rev_prior and rev_prior != 0:
            growth_context["revenue_growth_yoy"] = round(
                (rev_latest - rev_prior) / abs(rev_prior), 4
            )
        ni_latest = latest.get("net_income")
        ni_prior = prior.get("net_income")
        if ni_latest and ni_prior and ni_prior != 0:
            growth_context["net_income_growth_yoy"] = round(
                (ni_latest - ni_prior) / abs(ni_prior), 4
            )

    return {
        "source": "fundamentals",
        "status": "ok" if metrics else "limited",
        "metrics": metrics,
        "growth_context": growth_context,
    }


def _collect_thesis_signals(ticker: str) -> dict:
    """Thesis health signals from artifacts (≈ TradingAgents internal conviction)."""
    thesis = read_artifact_json(ticker, "thesis", "thesis.json")
    if not thesis:
        return {"source": "thesis", "status": "no_thesis"}

    health_checks = read_artifact_json(ticker, "thesis", "health_checks.json")
    latest_health = None
    if health_checks and health_checks.get("health_checks"):
        checks = health_checks["health_checks"]
        latest_health = checks[-1] if checks else None

    catalysts = read_artifact_json(ticker, "thesis", "catalysts.json")
    upcoming_catalysts = []
    today_str = date.today().isoformat()
    if catalysts and catalysts.get("entries"):
        upcoming_catalysts = [
            c for c in catalysts["entries"]
            if not c.get("resolved") and c.get("date", "") >= today_str
        ]

    return {
        "source": "thesis",
        "status": thesis.get("status", "unknown"),
        "position": thesis.get("position", "unknown"),
        "core_thesis": thesis.get("core_thesis", ""),
        "health_score": latest_health.get("overall_score") if latest_health else None,
        "health_grade": latest_health.get("grade") if latest_health else None,
        "assumption_count": len(thesis.get("assumptions", [])),
        "buy_reason_count": len(thesis.get("buy_reasons", [])),
        "upcoming_catalysts": upcoming_catalysts[:5],
    }


def _collect_risk_signals(ticker: str) -> dict:
    """Risk signals from API + artifacts (≈ TradingAgents Risk Management Team)."""
    risk_data = _get(f"/api/analysis/risk/{ticker}")

    # Portfolio-level risk alerts
    portfolio_risk = read_artifact_json("_portfolio", "risk", "risk_report.json")
    ticker_alerts = []
    if portfolio_risk and portfolio_risk.get("alerts"):
        ticker_alerts = [
            a for a in portfolio_risk["alerts"]
            if a.get("ticker") == ticker
        ]

    return {
        "source": "risk",
        "status": "ok" if risk_data else "unavailable",
        "beta": risk_data.get("beta") if risk_data else None,
        "max_drawdown": risk_data.get("max_drawdown") if risk_data else None,
        "sharpe": risk_data.get("sharpe_ratio") if risk_data else None,
        "volatility": risk_data.get("annualized_volatility") if risk_data else None,
        "active_alerts": ticker_alerts,
    }


def _collect_earnings_signals(ticker: str) -> dict:
    """Earnings signals from artifacts (≈ TradingAgents News/Sentiment Analyst)."""
    # Check for latest earnings analysis
    io = ArtifactIO(ticker, "earnings")
    earnings_files = io.list_files(".json")

    # Find most recent analysis
    latest_analysis = None
    for f in sorted(earnings_files, reverse=True):
        if "raw" not in f:
            data = io.read_json(f)
            if data:
                latest_analysis = data
                break

    # Check for earnings preview
    preview_files = [f for f in earnings_files if "preview" in f.lower()]
    has_preview = len(preview_files) > 0

    return {
        "source": "earnings",
        "status": "ok" if latest_analysis else "no_data",
        "latest_quarter": latest_analysis.get("quarter") if latest_analysis else None,
        "revenue_surprise_pct": latest_analysis.get("revenue_surprise_pct") if latest_analysis else None,
        "eps_surprise_pct": latest_analysis.get("eps_surprise_pct") if latest_analysis else None,
        "has_upcoming_preview": has_preview,
    }


def _collect_model_signals(ticker: str) -> dict:
    """Model / projection signals from artifacts."""
    projections = read_artifact_json(ticker, "model", "projections.json")
    if not projections:
        return {"source": "model", "status": "no_model"}

    return {
        "source": "model",
        "status": "ok",
        "target_price": projections.get("target_price"),
        "upside_pct": projections.get("upside_pct"),
        "scenario": projections.get("base_case", {}).get("scenario"),
    }


# ── Main collector ───────────────────────────────────────────


def collect(decision_date: date) -> bool:
    """Collect all signals for every portfolio position."""
    date_str = decision_date.isoformat()
    print(f"Collecting fund-manager signals for {date_str}...")

    # Get portfolio positions
    summary = _get("/api/portfolio/", {"portfolio_id": 1})
    if not summary:
        print("  ✗  Cannot reach portfolio API. Is the server running?")
        return False

    positions = _get("/api/portfolio/positions", {"portfolio_id": 1}) or []
    if not positions:
        print("  ⚠  No open positions in portfolio.")
        return False
    print(f"  ✓  {len(positions)} positions found")

    # Portfolio-level risk
    portfolio_risk = _post(
        "/api/analysis/risk/portfolio",
        {"portfolio_id": 1, "lookback_days": 252},
    )

    # Collect per-ticker signals (all 6 analyst roles)
    ticker_signals = {}
    for pos in positions:
        ticker = pos.get("ticker", "")
        if not ticker:
            continue
        print(f"  Collecting signals for {ticker}...")
        ticker_signals[ticker] = {
            "position_info": {
                "shares": pos.get("shares"),
                "avg_cost": pos.get("avg_cost"),
                "market_value": pos.get("market_value"),
                "weight": pos.get("weight"),
                "unrealized_pnl": pos.get("unrealized_pnl"),
                "unrealized_pnl_pct": pos.get("unrealized_pnl_pct"),
                "conviction": pos.get("conviction"),
            },
            "market": _collect_market_signals(ticker),
            "fundamentals": _collect_fundamental_signals(ticker),
            "thesis": _collect_thesis_signals(ticker),
            "risk": _collect_risk_signals(ticker),
            "earnings": _collect_earnings_signals(ticker),
            "model": _collect_model_signals(ticker),
        }
        print(f"    ✓ {ticker} — 6 signal sources collected")

    # Assemble raw data bundle
    raw = {
        "decision_date": date_str,
        "portfolio": {
            "total_value": summary.get("total_value"),
            "cash": summary.get("cash"),
            "cash_pct": summary.get("cash_pct"),
            "position_count": len(positions),
            "benchmark": summary.get("benchmark", "SPY"),
        },
        "portfolio_risk": portfolio_risk,
        "ticker_signals": ticker_signals,
        "collection_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    io = ArtifactIO("_portfolio", "decisions")
    path = io.write_json(f"{date_str}_signals.json", raw)
    print(f"\n  ✓  Signals written to {path}")
    return True


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect fund-manager signals")
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Decision date (YYYY-MM-DD)",
    )
    args = parser.parse_args()
    decision_date = date.fromisoformat(args.date)
    ok = collect(decision_date)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
