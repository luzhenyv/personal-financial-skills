#!/usr/bin/env python3
"""Task 1 — Collect pre-earnings data from REST API + thesis artifacts.

Gathers quarterly trends, metrics, segments, prices, and thesis context
into a single raw JSON for the AI scenario analysis.

Usage::

    uv run python skills/earnings-preview/scripts/collect_preview.py NVDA
    uv run python skills/earnings-preview/scripts/collect_preview.py NVDA --quarter Q1 --year 2026
"""

from __future__ import annotations

import argparse
import os
import sys
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


def _detect_next_quarter(quarterly: list[dict]) -> tuple[str, int] | None:
    """Predict the next reporting quarter from the latest available data."""
    if not quarterly:
        return None
    latest = quarterly[-1]
    fq = latest.get("fiscal_quarter")
    fy = latest.get("fiscal_year")
    if not fq or not fy:
        return None
    if fq < 4:
        return f"Q{fq + 1}", fy
    return "Q1", fy + 1


def collect(ticker: str, quarter: str | None, year: int | None) -> bool:
    """Collect all preview data and write raw JSON artifact."""
    ticker = ticker.upper()

    # Company check
    company = _get(f"/api/companies/{ticker}")
    if not company:
        print(f"  ✗  {ticker} not found. Run ETL first:")
        print(f"     uv run python -m pfs.etl.pipeline ingest {ticker} --years 5")
        return False

    print(f"Collecting earnings preview data for {ticker}...")

    # Quarterly financials (trend data)
    quarterly = _get(f"/api/financials/{ticker}/quarterly", {"quarters": 8}) or []
    print(f"  ✓  {len(quarterly)} quarters of data")

    # Detect upcoming quarter
    if quarter and year:
        q_label, q_year = quarter.upper(), year
    else:
        detected = _detect_next_quarter(quarterly)
        if detected:
            q_label, q_year = detected
        else:
            q_label, q_year = "Q?", 2026
    print(f"  Preview for: {q_label} {q_year}")

    # Metrics
    metrics = _get(f"/api/financials/{ticker}/metrics") or {}

    # Segments
    segments = _get(f"/api/financials/{ticker}/segments") or {}

    # Recent prices (3 months)
    prices = _get(f"/api/financials/{ticker}/prices", {"period": "3mo"}) or []

    # Thesis context
    thesis = read_artifact_json(ticker, "thesis", "thesis.json")
    catalysts = read_artifact_json(ticker, "thesis", "catalysts.json")
    health_checks = read_artifact_json(ticker, "thesis", "health_checks.json")

    latest_health = None
    if health_checks and health_checks.get("entries"):
        latest_health = health_checks["entries"][-1]

    thesis_context = None
    if thesis:
        thesis_context = {
            "thesis_statement": thesis.get("thesis", ""),
            "position": thesis.get("position", "long"),
            "conviction": thesis.get("conviction", "unset"),
            "key_pillars": thesis.get("key_pillars", []),
            "assumptions": thesis.get("assumptions", []),
            "sell_conditions": thesis.get("sell_conditions", []),
            "key_risks": thesis.get("key_risks", []),
            "latest_health_score": latest_health.get("composite_score") if latest_health else None,
        }
        print(f"  ✓  Thesis loaded (conviction: {thesis_context['conviction']})")
    else:
        print(f"  ⚠  No thesis found for {ticker}")

    # Compute simple trend stats from quarterly data
    trends = _compute_trends(quarterly)

    # Assemble raw data
    raw = {
        "ticker": ticker,
        "company_name": company.get("name", ticker),
        "sector": company.get("sector", ""),
        "industry": company.get("industry", ""),
        "preview_quarter": q_label,
        "preview_year": q_year,
        "quarterly_data": quarterly,
        "trends": trends,
        "metrics": metrics,
        "segments": segments,
        "recent_prices": prices[-60:] if len(prices) > 60 else prices,  # Last ~3 months
        "thesis_context": thesis_context,
        "catalysts": catalysts.get("entries", []) if catalysts else [],
    }

    # Write artifact
    io = ArtifactIO(ticker, "earnings")
    filename = f"preview_{q_label}_{q_year}_raw.json"
    path = io.write_json(filename, raw)
    print(f"\n✓  Raw data written to {path}")
    print(f"   Next: AI generates scenario framework from this data")
    return True


def _compute_trends(quarterly: list[dict]) -> dict:
    """Compute revenue/EPS growth trends from quarterly data."""
    if len(quarterly) < 2:
        return {}

    revenues = []
    eps_values = []
    gross_margins = []
    op_margins = []

    for q in quarterly:
        inc = q.get("income_statement") or q.get("income", {}) or {}
        revenues.append(inc.get("total_revenue") or inc.get("revenue"))
        eps_values.append(inc.get("eps_diluted") or inc.get("eps"))
        if inc.get("total_revenue") and inc.get("gross_profit"):
            rev = inc["total_revenue"]
            gp = inc["gross_profit"]
            gross_margins.append(gp / rev if rev else None)
        else:
            gross_margins.append(None)
        if inc.get("total_revenue") and inc.get("operating_income"):
            rev = inc["total_revenue"]
            oi = inc["operating_income"]
            op_margins.append(oi / rev if rev else None)
        else:
            op_margins.append(None)

    # YoY growth (compare Q vs Q-4 if available)
    yoy_rev_growth = None
    if len(revenues) >= 5 and revenues[-1] and revenues[-5]:
        yoy_rev_growth = (revenues[-1] - revenues[-5]) / abs(revenues[-5])

    # Sequential growth
    seq_rev_growth = None
    if len(revenues) >= 2 and revenues[-1] and revenues[-2]:
        seq_rev_growth = (revenues[-1] - revenues[-2]) / abs(revenues[-2])

    return {
        "yoy_revenue_growth": round(yoy_rev_growth, 4) if yoy_rev_growth is not None else None,
        "sequential_revenue_growth": round(seq_rev_growth, 4) if seq_rev_growth is not None else None,
        "latest_revenue": revenues[-1] if revenues else None,
        "latest_eps": eps_values[-1] if eps_values else None,
        "latest_gross_margin": round(gross_margins[-1], 4) if gross_margins and gross_margins[-1] else None,
        "latest_op_margin": round(op_margins[-1], 4) if op_margins and op_margins[-1] else None,
        "revenue_series": [r for r in revenues if r is not None],
        "eps_series": [e for e in eps_values if e is not None],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect pre-earnings data for preview")
    parser.add_argument("ticker", help="Company ticker (e.g. NVDA)")
    parser.add_argument("--quarter", help="Quarter label (e.g. Q1)")
    parser.add_argument("--year", type=int, help="Fiscal year (e.g. 2026)")
    args = parser.parse_args()

    success = collect(args.ticker, args.quarter, args.year)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
