#!/usr/bin/env python3
"""Idea Generation — Quantitative Stock Screener.

Scans all ingested companies against quantitative criteria and produces
a ranked list of investment idea candidates.

Usage::

    uv run python skills/idea-generation/scripts/screen.py --type growth
    uv run python skills/idea-generation/scripts/screen.py --type value --max-pe 15 --min-fcf-yield 0.05
    uv run python skills/idea-generation/scripts/screen.py --type quality
    uv run python skills/idea-generation/scripts/screen.py --type all
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── Path setup ───────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO, read_artifact_json

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30

io = ArtifactIO("_ideas", "")

# ── Screen definitions ───────────────────────────────────────

# Each screen defines (metric_name, operator, threshold, weight).
# operator: ">" means metric must be > threshold, "<" means < threshold.

SCREENS: dict[str, dict] = {
    "value": {
        "description": "Low valuation with positive fundamentals",
        "filters": [
            ("pe_ratio", "<", 20.0),
            ("ev_to_ebitda", "<", 12.0),
            ("fcf_yield", ">", 0.05),
            ("pb_ratio", "<", 2.0),
            ("revenue_growth", ">", 0.0),
        ],
        "scoring": [
            ("fcf_yield", 25),       # higher is better
            ("ev_to_ebitda", -20),   # lower is better (negative weight)
            ("pe_ratio", -20),       # lower is better
            ("revenue_growth", 15),
            ("operating_margin", 10),
            ("roe", 10),
        ],
    },
    "growth": {
        "description": "High growth with reasonable economics",
        "filters": [
            ("revenue_growth", ">", 0.15),
            ("eps_growth", ">", 0.20),
            ("operating_margin", ">", 0.10),
            ("roic", ">", 0.15),
        ],
        "scoring": [
            ("revenue_growth", 30),
            ("eps_growth", 25),
            ("operating_margin", 15),
            ("roic", 15),
            ("fcf_yield", 10),
            ("pe_ratio", -5),
        ],
    },
    "quality": {
        "description": "Consistent, high-return businesses",
        "filters": [
            ("revenue_growth", ">", 0.0),
            ("operating_margin", ">", 0.15),
            ("roe", ">", 0.15),
            ("debt_to_equity", "<", 1.0),
            ("fcf_yield", ">", 0.02),
        ],
        "scoring": [
            ("roe", 25),
            ("roic", 20),
            ("operating_margin", 20),
            ("fcf_yield", 15),
            ("revenue_growth", 10),
            ("debt_to_equity", -10),
        ],
    },
    "special-situation": {
        "description": "High growth at low valuations — potential mispricing",
        "filters": [
            ("revenue_growth", ">", 0.25),
            ("pe_ratio", "<", 25.0),
        ],
        "scoring": [
            ("revenue_growth", 30),
            ("pe_ratio", -25),
            ("operating_margin", 20),
            ("eps_growth", 15),
            ("fcf_yield", 10),
        ],
    },
}


# ── API helpers ──────────────────────────────────────────────


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


# ── Screening logic ──────────────────────────────────────────


def _latest_metrics(metrics_list: list[dict]) -> dict | None:
    """Extract the most recent annual metrics row."""
    if not metrics_list:
        return None
    # metrics are returned oldest-first; take the last one
    return metrics_list[-1]


def _passes_filter(
    metrics: dict,
    filters: list[tuple[str, str, float]],
) -> tuple[bool, list[str]]:
    """Check if a company's metrics pass all screen filters.

    Returns (pass_bool, list_of_failed_filter_names).
    """
    failures: list[str] = []
    for metric_name, op, threshold in filters:
        val = metrics.get(metric_name)
        if val is None:
            failures.append(f"{metric_name}=None")
            continue
        val = float(val)
        if op == ">" and val <= threshold:
            failures.append(f"{metric_name}={val:.4f} (need >{threshold})")
        elif op == "<" and val >= threshold:
            failures.append(f"{metric_name}={val:.4f} (need <{threshold})")
    return len(failures) == 0, failures


def _compute_score(
    metrics: dict,
    scoring: list[tuple[str, int]],
) -> float:
    """Compute a weighted score for ranking.

    Positive weights reward higher values; negative weights reward lower values.
    All metric values are normalized to [0, 1] range using simple sigmoid-like scaling.
    """
    total = 0.0
    weight_sum = 0.0

    for metric_name, weight in scoring:
        val = metrics.get(metric_name)
        if val is None:
            continue
        val = float(val)
        abs_weight = abs(weight)

        # Simple normalization: map common ranges to 0-1
        if metric_name in ("revenue_growth", "eps_growth", "operating_income_growth", "net_income_growth"):
            # Growth: 0% → 0.0, 50% → 1.0
            normalized = min(max(val / 0.50, -1.0), 2.0) / 2.0 + 0.5
        elif metric_name in ("operating_margin", "net_margin", "gross_margin", "ebitda_margin", "fcf_margin"):
            # Margins: 0% → 0.0, 40% → 1.0
            normalized = min(max(val / 0.40, 0.0), 1.0)
        elif metric_name in ("roe", "roa", "roic"):
            # Returns: 0% → 0.0, 30% → 1.0
            normalized = min(max(val / 0.30, 0.0), 1.0)
        elif metric_name in ("pe_ratio",):
            # P/E: 5 → 1.0, 60 → 0.0
            normalized = max(1.0 - (val - 5.0) / 55.0, 0.0)
        elif metric_name in ("ev_to_ebitda",):
            # EV/EBITDA: 3 → 1.0, 40 → 0.0
            normalized = max(1.0 - (val - 3.0) / 37.0, 0.0)
        elif metric_name in ("pb_ratio",):
            # P/B: 0.5 → 1.0, 10 → 0.0
            normalized = max(1.0 - (val - 0.5) / 9.5, 0.0)
        elif metric_name in ("fcf_yield",):
            # FCF yield: 0% → 0.0, 10% → 1.0
            normalized = min(max(val / 0.10, 0.0), 1.0)
        elif metric_name in ("debt_to_equity",):
            # D/E: 0 → 1.0, 3 → 0.0
            normalized = max(1.0 - val / 3.0, 0.0)
        else:
            normalized = 0.5  # unknown metric — neutral

        if weight < 0:
            # For negative weights, we want lower raw values to score higher
            # The normalization already handles this for inverted metrics
            normalized = 1.0 - normalized

        total += normalized * abs_weight
        weight_sum += abs_weight

    return round((total / weight_sum) * 100, 1) if weight_sum > 0 else 0.0


def _generate_flags(metrics: dict) -> list[str]:
    """Generate human-readable flags based on metric values."""
    flags: list[str] = []
    m = {k: float(v) for k, v in metrics.items() if v is not None}

    if m.get("revenue_growth", 0) > 0.25:
        flags.append("high_revenue_growth")
    if m.get("eps_growth", 0) > 0.30:
        flags.append("strong_eps_growth")
    if m.get("operating_margin", 0) > 0.25:
        flags.append("high_margins")
    if m.get("roic", 0) > 0.20:
        flags.append("high_roic")
    if m.get("roe", 0) > 0.25:
        flags.append("high_roe")
    if m.get("fcf_yield", 0) > 0.06:
        flags.append("strong_fcf_yield")
    if m.get("debt_to_equity", 999) < 0.3:
        flags.append("low_leverage")
    if m.get("pe_ratio", 999) < 15:
        flags.append("low_pe")
    if m.get("ev_to_ebitda", 999) < 10:
        flags.append("low_ev_ebitda")

    return flags


# ── Override helpers ─────────────────────────────────────────


def _apply_overrides(
    screen_def: dict,
    overrides: dict[str, float],
) -> dict:
    """Apply CLI overrides (e.g. --max-pe 15) to screen filters."""
    override_map = {
        "max_pe": ("pe_ratio", "<"),
        "min_pe": ("pe_ratio", ">"),
        "max_ev_ebitda": ("ev_to_ebitda", "<"),
        "min_fcf_yield": ("fcf_yield", ">"),
        "max_debt_equity": ("debt_to_equity", "<"),
        "min_revenue_growth": ("revenue_growth", ">"),
        "min_operating_margin": ("operating_margin", ">"),
        "min_roe": ("roe", ">"),
        "min_roic": ("roic", ">"),
    }
    if not overrides:
        return screen_def

    new_filters = list(screen_def["filters"])
    for key, value in overrides.items():
        if key in override_map and value is not None:
            metric, op = override_map[key]
            # Replace existing filter for this metric, or add new one
            new_filters = [(m, o, t) for m, o, t in new_filters if m != metric]
            new_filters.append((metric, op, value))

    return {**screen_def, "filters": new_filters}


# ── Main screening pipeline ─────────────────────────────────


def run_screen(
    screen_type: str,
    overrides: dict[str, float] | None = None,
    *,
    verbose: bool = False,
) -> dict:
    """Run a screen across all ingested companies.

    Returns the screen results dict ready for artifact storage.
    """
    if screen_type == "all":
        # Run all screens and merge results
        all_results: list[dict] = []
        seen: set[str] = set()
        for stype in SCREENS:
            sub = run_screen(stype, overrides, verbose=verbose)
            for r in sub.get("results", []):
                if r["ticker"] not in seen:
                    r["screen_type"] = stype
                    all_results.append(r)
                    seen.add(r["ticker"])
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return {
            "screen_type": "all",
            "screen_params": {},
            "screened_at": datetime.now(timezone.utc).isoformat(),
            "total_companies": sum(1 for _ in seen) or 0,
            "passes": len(all_results),
            "results": all_results,
        }

    if screen_type not in SCREENS:
        print(f"  ✗  Unknown screen type: {screen_type}", file=sys.stderr)
        print(f"     Available: {', '.join(SCREENS.keys())}, all", file=sys.stderr)
        sys.exit(1)

    screen_def = SCREENS[screen_type]
    if overrides:
        screen_def = _apply_overrides(screen_def, overrides)

    print(f"\n{'='*60}")
    print(f"  Idea Generation — {screen_type.upper()} Screen")
    print(f"  {screen_def['description']}")
    print(f"{'='*60}\n")

    with httpx.Client(base_url=API_URL) as client:
        # 1. Fetch all companies
        print("  Fetching companies…")
        companies = _get(client, "/api/companies/")
        if not companies:
            print("  ✗  No companies found. Run ETL first.", file=sys.stderr)
            sys.exit(1)

        print(f"  Found {len(companies)} companies\n")

        # 2. Screen each company
        results: list[dict] = []
        for comp in companies:
            ticker = comp.get("ticker", "")
            name = comp.get("name", "")
            sector = comp.get("sector", "")

            metrics_list = _get(client, f"/api/financials/{ticker}/metrics")
            if not metrics_list:
                if verbose:
                    print(f"  ⏭  {ticker:6s} — no metrics data")
                continue

            latest = _latest_metrics(metrics_list)
            if not latest:
                if verbose:
                    print(f"  ⏭  {ticker:6s} — no annual metrics")
                continue

            passes, failures = _passes_filter(latest, screen_def["filters"])

            if not passes:
                if verbose:
                    print(f"  ✗  {ticker:6s} — failed: {', '.join(failures[:3])}")
                continue

            score = _compute_score(latest, screen_def["scoring"])
            flags = _generate_flags(latest)

            # Extract key metrics for the result
            key_metrics = {}
            for field in (
                "revenue_growth", "eps_growth", "operating_margin",
                "net_margin", "gross_margin", "roic", "roe",
                "pe_ratio", "ev_to_ebitda", "pb_ratio", "fcf_yield",
                "debt_to_equity", "current_ratio",
            ):
                val = latest.get(field)
                if val is not None:
                    key_metrics[field] = float(val)

            results.append({
                "ticker": ticker,
                "name": name,
                "sector": sector,
                "score": score,
                "metrics": key_metrics,
                "flags": flags,
                "thesis_hint": "",  # Populated by generate_ideas.py (AI step)
            })
            print(f"  ✓  {ticker:6s} — score {score:5.1f}  [{', '.join(flags[:3])}]")

    # 3. Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)

    # 4. Build output
    output = {
        "screen_type": screen_type,
        "screen_params": {
            "filters": [
                {"metric": m, "op": o, "threshold": t}
                for m, o, t in screen_def["filters"]
            ],
        },
        "screened_at": datetime.now(timezone.utc).isoformat(),
        "total_companies": len(companies),
        "passes": len(results),
        "results": results,
    }

    print(f"\n  {'─'*40}")
    print(f"  Screen complete: {len(results)}/{len(companies)} companies passed")

    if results:
        print(f"\n  Top candidates:")
        for r in results[:5]:
            print(f"    {r['ticker']:6s}  score={r['score']:5.1f}  sector={r['sector']}")

    return output


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Idea Generation — Quantitative Stock Screener",
    )
    parser.add_argument(
        "--type",
        choices=list(SCREENS.keys()) + ["all"],
        default="growth",
        help="Screen type (default: growth)",
    )
    parser.add_argument("--max-pe", type=float, default=None)
    parser.add_argument("--min-pe", type=float, default=None)
    parser.add_argument("--max-ev-ebitda", type=float, default=None)
    parser.add_argument("--min-fcf-yield", type=float, default=None)
    parser.add_argument("--max-debt-equity", type=float, default=None)
    parser.add_argument("--min-revenue-growth", type=float, default=None)
    parser.add_argument("--min-operating-margin", type=float, default=None)
    parser.add_argument("--min-roe", type=float, default=None)
    parser.add_argument("--min-roic", type=float, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    overrides = {
        "max_pe": args.max_pe,
        "min_pe": args.min_pe,
        "max_ev_ebitda": args.max_ev_ebitda,
        "min_fcf_yield": args.min_fcf_yield,
        "max_debt_equity": args.max_debt_equity,
        "min_revenue_growth": args.min_revenue_growth,
        "min_operating_margin": args.min_operating_margin,
        "min_roe": args.min_roe,
        "min_roic": args.min_roic,
    }
    # Strip None values
    overrides = {k: v for k, v in overrides.items() if v is not None}

    results = run_screen(args.type, overrides or None, verbose=args.verbose)

    # Write artifact
    path = io.write_json("screen_results.json", results)
    print(f"\n  ✓  Wrote {path}\n")


if __name__ == "__main__":
    main()
