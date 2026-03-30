"""
Task 1: Collect Earnings Data
==============================
Fetch quarterly financial data from the REST API and write raw JSON
to the earnings artifact directory.

Usage:
    uv run python skills/earnings-analysis/scripts/collect_earnings.py NVDA
    uv run python skills/earnings-analysis/scripts/collect_earnings.py NVDA --quarter Q4 --year 2024
    uv run python skills/earnings-analysis/scripts/collect_earnings.py AAPL --quarters 12
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import httpx

from artifact_io import ArtifactIO

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


def _get(path: str, params: dict | None = None) -> dict | list | None:
    """GET from the REST API. Returns parsed JSON or None on error."""
    url = f"{API_URL}{path}"
    try:
        resp = httpx.get(url, params=params or {}, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        print(f"  ⚠ {path} returned {resp.status_code}: {resp.text[:200]}")
    except httpx.HTTPError as e:
        print(f"  ✗ {path} failed: {e}")
    return None


def _detect_latest_quarter(quarterly_data: list[dict]) -> tuple[str, int] | None:
    """Detect the latest quarter from quarterly data.

    Returns (quarter_label, fiscal_year) e.g. ("Q4", 2024) or None.
    """
    if not quarterly_data:
        return None
    latest = quarterly_data[-1]
    fq = latest.get("fiscal_quarter")
    fy = latest.get("fiscal_year")
    if fq and fy:
        return f"Q{fq}", fy
    return None


def collect(ticker: str, quarter: str | None, year: int | None, num_quarters: int) -> bool:
    """Collect all earnings data for a ticker and write raw JSON artifact.

    Returns True on success, False on failure.
    """
    ticker = ticker.upper()
    print(f"\n{'='*60}")
    print(f"  Earnings Data Collection: {ticker}")
    print(f"{'='*60}\n")

    # 1. Verify company exists
    print("1. Verifying company exists...")
    company = _get(f"/api/companies/{ticker}")
    if not company:
        print(f"\n✗ Company {ticker} not found in database.")
        print(f"  Run: uv run python -m pfs.etl.pipeline ingest {ticker} --years 5")
        return False
    print(f"   ✓ {company.get('name', ticker)} ({company.get('sector', 'N/A')})")

    # 2. Fetch quarterly data
    print(f"\n2. Fetching quarterly data (last {num_quarters} quarters)...")
    quarterly = _get(f"/api/financials/{ticker}/quarterly", {"quarters": num_quarters})
    if not quarterly:
        print("   ⚠ No quarterly data available. Check if quarterly data has been ingested.")
        quarterly = []

    # Auto-detect quarter if not specified
    if not quarter or not year:
        detected = _detect_latest_quarter(quarterly)
        if detected:
            quarter = quarter or detected[0]
            year = year or detected[1]
            print(f"   Auto-detected latest quarter: {quarter} FY{year}")
        else:
            # Fall back to current date
            today = date.today()
            current_q = (today.month - 1) // 3 + 1
            quarter = quarter or f"Q{current_q}"
            year = year or today.year
            print(f"   No quarterly data; using current period: {quarter} {year}")

    print(f"   Analyzing: {quarter} FY{year}")
    print(f"   Quarters fetched: {len(quarterly)}")

    # 3. Fetch annual income statements for YoY comparison
    print("\n3. Fetching annual income statements (2 years)...")
    annual_income = _get(f"/api/financials/{ticker}/income-statements", {"years": 2})
    print(f"   Annual periods: {len(annual_income or [])}")

    # 4. Fetch metrics
    print("\n4. Fetching financial metrics...")
    metrics = _get(f"/api/financials/{ticker}/metrics")
    print(f"   Metric periods: {len(metrics or [])}")

    # 5. Fetch segments
    print("\n5. Fetching segment data...")
    segments = _get(f"/api/financials/{ticker}/segments")
    print(f"   Segments: {len(segments or [])}")

    # 6. Fetch latest 10-Q filing metadata
    print("\n6. Fetching 10-Q filing metadata...")
    filings_10q = _get(f"/api/filings/{ticker}", {"form_type": "10-Q"})
    latest_10q = filings_10q[0] if filings_10q else None
    if latest_10q:
        print(f"   Latest 10-Q: filed {latest_10q.get('filing_date', 'N/A')}")
    else:
        print("   ⚠ No 10-Q filings found")

    # 7. Fetch recent price action
    print("\n7. Fetching recent price data (3 months)...")
    prices = _get(f"/api/financials/{ticker}/prices", {"period": "3m"})
    print(f"   Price data points: {len(prices or [])}")

    # 8. Check for existing thesis
    print("\n8. Checking for investment thesis...")
    io_thesis = ArtifactIO(ticker, "thesis")
    thesis = io_thesis.read_json("thesis.json")
    if thesis:
        print(f"   ✓ Thesis found (health: {thesis.get('health_score', 'N/A')})")
    else:
        print("   — No thesis tracked for this company")

    # ── Assemble raw data artifact ───────────────────────────────────────

    raw_data = {
        "ticker": ticker,
        "quarter": quarter,
        "fiscal_year": year,
        "collection_date": date.today().isoformat(),
        "company": company,
        "quarterly_data": quarterly,
        "annual_income": annual_income or [],
        "metrics": metrics or [],
        "segments": segments or [],
        "latest_10q": latest_10q,
        "recent_prices": prices or [],
        "thesis_exists": thesis is not None,
        "thesis_summary": {
            "statement": thesis.get("thesis_statement", ""),
            "health_score": thesis.get("health_score"),
            "pillars": [p.get("title", "") for p in thesis.get("pillars", [])],
        } if thesis else None,
    }

    # ── Freshness check ─────────────────────────────────────────────────

    print("\n─── Freshness Check ───")
    if quarterly:
        latest_q = quarterly[-1]
        data_quarter = f"Q{latest_q.get('fiscal_quarter')}"
        data_year = latest_q.get("fiscal_year")
        if data_quarter == quarter and data_year == year:
            print(f"   ✓ Data matches target quarter ({quarter} FY{year})")
            raw_data["freshness_check"] = "pass"
        else:
            print(f"   ⚠ Latest data is {data_quarter} FY{data_year}, "
                  f"but analyzing {quarter} FY{year}")
            print(f"   Consider re-running ETL: "
                  f"uv run python -m pfs.etl.pipeline ingest {ticker} --years 5")
            raw_data["freshness_check"] = "stale"
    else:
        print("   ⚠ No quarterly data — freshness check skipped")
        raw_data["freshness_check"] = "no_data"

    # ── Write artifact ───────────────────────────────────────────────────

    io = ArtifactIO(ticker, "earnings")
    filename = f"{quarter}_{year}_raw.json"
    path = io.write_json(filename, raw_data)

    print(f"\n{'='*60}")
    print(f"  ✓ Raw data written to: {path}")
    print(f"{'='*60}\n")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect earnings data from REST API for analysis.",
    )
    parser.add_argument("ticker", help="Company ticker (e.g. NVDA)")
    parser.add_argument("--quarter", help="Quarter label (e.g. Q4). Auto-detected if omitted.")
    parser.add_argument("--year", type=int, help="Fiscal year (e.g. 2024). Auto-detected if omitted.")
    parser.add_argument("--quarters", type=int, default=8,
                        help="Number of historical quarters to fetch (default: 8)")
    args = parser.parse_args()

    success = collect(args.ticker, args.quarter, args.year, args.quarters)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
