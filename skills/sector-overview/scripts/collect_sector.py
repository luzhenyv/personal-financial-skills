#!/usr/bin/env python3
"""Collect sector-level data from the REST API.

Fetches all companies, groups by sector, retrieves per-company metrics,
and computes sector aggregates (medians, ranges, totals). Writes
``sector_data.json`` for each sector.

Usage::

    # Single sector
    uv run python skills/sector-overview/scripts/collect_sector.py --sector Technology

    # List available sectors
    uv run python skills/sector-overview/scripts/collect_sector.py --list

    # All sectors with at least 3 companies
    uv run python skills/sector-overview/scripts/collect_sector.py --all --min-companies 3
"""

from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
from datetime import datetime, timezone

import httpx

from artifact_io import ArtifactIO

API_URL = os.getenv("PFS_API_URL", "http://localhost:8000")

# ── Helpers ──────────────────────────────────────────────────────────────────


def _get(client: httpx.Client, path: str, **params) -> dict | list | None:
    """GET helper with error handling."""
    try:
        r = client.get(f"{API_URL}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPStatusError, httpx.ConnectError) as exc:
        print(f"  WARN: {path} → {exc}")
        return None


def slugify(sector: str) -> str:
    """Convert sector name to a URL-safe slug."""
    s = sector.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def safe_float(val) -> float | None:
    """Convert value to float, returning None for non-numeric."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def median_of(values: list[float | None]) -> float | None:
    """Compute median of non-None values."""
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return statistics.median(clean)


def mean_of(values: list[float | None]) -> float | None:
    """Compute mean of non-None values."""
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return statistics.mean(clean)


# ── Metric keys we care about ───────────────────────────────────────────────

METRIC_KEYS = [
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "ebitda_margin",
    "net_margin",
    "fcf_margin",
    "roe",
    "roa",
    "roic",
    "pe_ratio",
    "ps_ratio",
    "pb_ratio",
    "ev_to_ebitda",
    "fcf_yield",
    "debt_to_equity",
    "current_ratio",
    "eps_growth",
]


# ── Core collection ─────────────────────────────────────────────────────────


def fetch_all_companies(client: httpx.Client) -> list[dict]:
    """Fetch the full company list."""
    data = _get(client, "/api/companies/")
    if not data:
        print("ERROR: Could not fetch companies list.")
        sys.exit(1)
    return data


def group_by_sector(companies: list[dict]) -> dict[str, list[dict]]:
    """Group companies by their sector field."""
    sectors: dict[str, list[dict]] = {}
    for c in companies:
        sector = c.get("sector") or "Unknown"
        sectors.setdefault(sector, []).append(c)
    return sectors


def fetch_company_metrics(client: httpx.Client, ticker: str) -> dict | None:
    """Fetch financial metrics for a single company."""
    data = _get(client, f"/api/financials/{ticker}/metrics")
    if not data:
        return None
    # API may return a list (multiple years) — take latest
    if isinstance(data, list):
        return data[0] if data else None
    return data


def fetch_latest_revenue(client: httpx.Client, ticker: str) -> float | None:
    """Fetch the most recent annual revenue."""
    data = _get(client, f"/api/financials/{ticker}/income-statements", years=1)
    if not data:
        return None
    if isinstance(data, list) and data:
        return safe_float(data[0].get("revenue"))
    return safe_float(data.get("revenue"))


def collect_sector(client: httpx.Client, sector: str, companies: list[dict]) -> dict:
    """Collect comprehensive data for one sector."""
    sector_slug = slugify(sector)
    print(f"\n{'='*60}")
    print(f"Collecting sector: {sector} ({len(companies)} companies)")
    print(f"{'='*60}")

    company_records = []
    for comp in sorted(companies, key=lambda c: c.get("market_cap") or 0, reverse=True):
        ticker = comp["ticker"]
        print(f"  Fetching {ticker}...")

        metrics_raw = fetch_company_metrics(client, ticker)
        revenue = fetch_latest_revenue(client, ticker)

        metrics = {}
        if metrics_raw:
            for key in METRIC_KEYS:
                metrics[key] = safe_float(metrics_raw.get(key))
        if revenue is not None:
            metrics["revenue"] = revenue

        company_records.append(
            {
                "ticker": ticker,
                "name": comp.get("name", ticker),
                "industry": comp.get("industry", ""),
                "market_cap": safe_float(comp.get("market_cap")),
                "metrics": metrics,
            }
        )

    # ── Compute aggregates ───────────────────────────────────────────
    aggregates = {}
    for key in METRIC_KEYS + ["revenue"]:
        values = [c["metrics"].get(key) for c in company_records]
        aggregates[f"median_{key}"] = median_of(values)
        aggregates[f"mean_{key}"] = mean_of(values)

    # Total market cap
    caps = [c["market_cap"] for c in company_records if c["market_cap"]]
    aggregates["total_market_cap"] = sum(caps) if caps else None
    aggregates["company_count"] = len(company_records)

    # ── Subsector (industry) grouping ────────────────────────────────
    subsectors: dict[str, list[str]] = {}
    for c in company_records:
        ind = c["industry"] or "Other"
        subsectors.setdefault(ind, []).append(c["ticker"])

    # ── Valuation range ──────────────────────────────────────────────
    pe_vals = [c["metrics"].get("pe_ratio") for c in company_records
               if c["metrics"].get("pe_ratio") is not None and c["metrics"]["pe_ratio"] > 0]
    ev_vals = [c["metrics"].get("ev_to_ebitda") for c in company_records
               if c["metrics"].get("ev_to_ebitda") is not None and c["metrics"]["ev_to_ebitda"] > 0]

    valuation_range = {
        "pe_low": min(pe_vals) if pe_vals else None,
        "pe_high": max(pe_vals) if pe_vals else None,
        "pe_median": median_of(pe_vals),
        "ev_ebitda_low": min(ev_vals) if ev_vals else None,
        "ev_ebitda_high": max(ev_vals) if ev_vals else None,
        "ev_ebitda_median": median_of(ev_vals),
    }

    result = {
        "sector": sector,
        "sector_slug": sector_slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company_count": len(company_records),
        "companies": company_records,
        "sector_aggregates": aggregates,
        "subsectors": subsectors,
        "valuation_range": valuation_range,
    }

    # ── Write artifact ───────────────────────────────────────────────
    io = ArtifactIO("_sectors", sector_slug)
    out = io.write_json("sector_data.json", result)
    print(f"  ✓ Wrote {out}")

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Collect sector-level financial data from the REST API."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sector", type=str, help="Sector name (e.g. 'Technology')")
    group.add_argument("--list", action="store_true", help="List all available sectors")
    group.add_argument("--all", action="store_true", help="Collect data for all sectors")
    parser.add_argument(
        "--min-companies",
        type=int,
        default=1,
        help="Minimum companies for --all mode (default: 1)",
    )
    args = parser.parse_args()

    with httpx.Client() as client:
        companies = fetch_all_companies(client)
        sectors = group_by_sector(companies)

        if args.list:
            print(f"\nAvailable sectors ({len(sectors)}):\n")
            for name, comps in sorted(sectors.items(), key=lambda x: -len(x[1])):
                tickers = ", ".join(c["ticker"] for c in comps[:5])
                suffix = "..." if len(comps) > 5 else ""
                print(f"  {name:30s}  {len(comps):2d} companies  ({tickers}{suffix})")
            return

        if args.sector:
            # Case-insensitive match
            matched = None
            for name in sectors:
                if name.lower() == args.sector.lower():
                    matched = name
                    break
            if not matched:
                print(f"ERROR: Sector '{args.sector}' not found.")
                print(f"Available: {', '.join(sorted(sectors))}")
                sys.exit(1)
            collect_sector(client, matched, sectors[matched])
            print("\nDone.")
            return

        if args.all:
            collected = 0
            for name, comps in sorted(sectors.items(), key=lambda x: -len(x[1])):
                if len(comps) < args.min_companies:
                    print(f"  Skipping {name} ({len(comps)} < {args.min_companies})")
                    continue
                collect_sector(client, name, comps)
                collected += 1
            print(f"\nDone. Collected {collected} sector(s).")


if __name__ == "__main__":
    main()
