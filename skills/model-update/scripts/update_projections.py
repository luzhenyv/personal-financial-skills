#!/usr/bin/env python3
"""Generate or update projections.json and model_update.md.

Reads model_data_raw.json, builds/updates forward estimates, and renders
a markdown change summary.

Usage:
    uv run python skills/model-update/scripts/update_projections.py TICKER
    uv run python skills/model-update/scripts/update_projections.py TICKER --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO  # noqa: E402

API_URL = os.getenv("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


def _fmt(val: float | int | None, prefix: str = "$", suffix: str = "") -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 1e9:
        return f"{prefix}{val / 1e9:.1f}B{suffix}"
    if abs(val) >= 1e6:
        return f"{prefix}{val / 1e6:.1f}M{suffix}"
    return f"{prefix}{val:,.2f}{suffix}"


def _pct(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.1f}%"


def update(ticker: str, persist: bool = False) -> None:
    ticker = ticker.upper()
    io = ArtifactIO(ticker, "model")

    raw = io.read_json("model_data_raw.json")
    if not raw:
        print(f"ERROR: No model_data_raw.json for {ticker}. Run collect_model_data.py first.")
        sys.exit(1)

    print(f"Updating projections for {ticker} ...")

    # --- Extract key actuals ---
    annual = raw.get("annual") or []
    quarterly = raw.get("quarterly") or []
    metrics = raw.get("metrics") or {}
    ttm = raw.get("ttm") or {}
    current_price = raw.get("current_price")
    existing = raw.get("existing_projections")

    # Determine base year from most recent annual
    if annual:
        base_year = max(int(a.get("fiscal_year", 0)) for a in annual)
    else:
        base_year = datetime.now().year

    fy1 = base_year + 1
    fy2 = base_year + 2

    # --- Compute growth trends from annual data ---
    rev_growth_rates = []
    for i in range(1, len(annual)):
        prev_rev = annual[i].get("revenue")
        curr_rev = annual[i - 1].get("revenue")  # annual[0] is most recent
        if prev_rev and curr_rev and prev_rev > 0:
            rev_growth_rates.append((curr_rev - prev_rev) / prev_rev)

    avg_rev_growth = sum(rev_growth_rates) / len(rev_growth_rates) if rev_growth_rates else None

    # Latest margins from metrics
    gross_margin = metrics.get("gross_margin")
    op_margin = metrics.get("operating_margin")

    # Latest annual actuals
    latest_annual = annual[0] if annual else {}
    latest_revenue = latest_annual.get("revenue")
    latest_ebitda = latest_annual.get("ebitda")
    latest_eps = latest_annual.get("eps_diluted") or latest_annual.get("eps")

    # --- Build estimates (simple trend extrapolation) ---
    if latest_revenue and avg_rev_growth is not None:
        fy1_revenue = latest_revenue * (1 + avg_rev_growth)
        fy2_revenue = fy1_revenue * (1 + avg_rev_growth)
    else:
        fy1_revenue = None
        fy2_revenue = None

    if latest_eps and avg_rev_growth is not None:
        fy1_eps = latest_eps * (1 + avg_rev_growth)
        fy2_eps = fy1_eps * (1 + avg_rev_growth)
    else:
        fy1_eps = None
        fy2_eps = None

    if latest_ebitda and avg_rev_growth is not None:
        fy1_ebitda = latest_ebitda * (1 + avg_rev_growth)
        fy2_ebitda = fy1_ebitda * (1 + avg_rev_growth)
    else:
        fy1_ebitda = None
        fy2_ebitda = None

    # Valuation
    fwd_pe = (current_price / fy1_eps) if (current_price and fy1_eps and fy1_eps > 0) else None
    ev_ebitda = None  # Would need enterprise value; skip for simplicity

    implied_price = None
    upside_pct = None
    target_pe = metrics.get("pe_ratio")  # use current as baseline target
    if target_pe and fy1_eps:
        implied_price = target_pe * fy1_eps
        if current_price and current_price > 0:
            upside_pct = (implied_price - current_price) / current_price

    # --- Build revision history entry ---
    revision_entry = {
        "date": datetime.now(timezone.utc).isoformat(),
        "trigger": "model_update",
        "changes": [],
    }

    old_projections = existing or {}
    old_estimates = old_projections.get("estimates", {})
    old_fy1 = old_estimates.get(f"FY{fy1}", {})
    if old_fy1.get("revenue") and fy1_revenue:
        rev_delta = (fy1_revenue - old_fy1["revenue"]) / old_fy1["revenue"]
        if abs(rev_delta) > 0.01:
            revision_entry["changes"].append(f"FY{fy1} revenue revised {rev_delta:+.1%}")
    if old_fy1.get("eps") and fy1_eps:
        eps_delta = (fy1_eps - old_fy1["eps"]) / abs(old_fy1["eps"])
        if abs(eps_delta) > 0.01:
            revision_entry["changes"].append(f"FY{fy1} EPS revised {eps_delta:+.1%}")

    revision_history = old_projections.get("revision_history", [])
    if revision_entry["changes"]:
        revision_history.append(revision_entry)

    # --- Write projections.json ---
    projections = {
        "ticker": ticker,
        "base_year": base_year,
        "estimates": {
            f"FY{fy1}": {
                "revenue": fy1_revenue,
                "ebitda": fy1_ebitda,
                "eps": round(fy1_eps, 2) if fy1_eps else None,
                "gross_margin": gross_margin,
                "op_margin": op_margin,
            },
            f"FY{fy2}": {
                "revenue": fy2_revenue,
                "ebitda": fy2_ebitda,
                "eps": round(fy2_eps, 2) if fy2_eps else None,
                "gross_margin": gross_margin,
                "op_margin": op_margin,
            },
        },
        "assumptions": {
            "revenue_growth": avg_rev_growth,
            "margin_trajectory": "stable" if gross_margin else "unknown",
            "share_count_trend": "stable",
            "key_drivers": [],
        },
        "valuation": {
            "target_pe": target_pe,
            "target_ev_ebitda": ev_ebitda,
            "forward_pe": round(fwd_pe, 1) if fwd_pe else None,
            "implied_price": round(implied_price, 2) if implied_price else None,
            "current_price": current_price,
            "upside_pct": round(upside_pct, 4) if upside_pct else None,
        },
        "revision_history": revision_history,
    }
    proj_path = io.write_json("projections.json", projections)
    print(f"  Projections → {proj_path}")

    # --- Render markdown summary ---
    lines = [
        f"# Model Update — {ticker}",
        f"*Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "## Trailing Actuals",
        "",
        f"| Metric | FY{base_year} Actual | TTM |",
        "|--------|--------------|-----|",
        f"| Revenue | {_fmt(latest_revenue)} | {_fmt(ttm.get('revenue'))} |",
        f"| Net Income | {_fmt(latest_annual.get('net_income'))} | {_fmt(ttm.get('net_income'))} |",
        f"| EPS (diluted) | {_fmt(latest_eps, prefix='$')} | {_fmt(ttm.get('eps'), prefix='$')} |",
        "",
        "## Forward Estimates",
        "",
        f"| Metric | FY{fy1}E | FY{fy2}E |",
        "|--------|---------|---------|",
        f"| Revenue | {_fmt(fy1_revenue)} | {_fmt(fy2_revenue)} |",
        f"| EBITDA | {_fmt(fy1_ebitda)} | {_fmt(fy2_ebitda)} |",
        f"| EPS | {_fmt(fy1_eps, prefix='$')} | {_fmt(fy2_eps, prefix='$')} |",
        f"| Gross Margin | {_pct(gross_margin)} | {_pct(gross_margin)} |",
        f"| Op Margin | {_pct(op_margin)} | {_pct(op_margin)} |",
        "",
        "## Key Assumptions",
        "",
        f"- **Revenue growth rate**: {_pct(avg_rev_growth)} (historical average)",
        f"- **Margin trajectory**: {'Stable' if gross_margin else 'Unknown'}",
        "- **Share count**: Stable",
        "",
        "## Valuation",
        "",
        f"- Current price: **{_fmt(current_price)}**",
        f"- Forward P/E (FY{fy1}): **{fwd_pe:.1f}x**" if fwd_pe else "- Forward P/E: N/A",
        f"- Target P/E: **{target_pe:.1f}x**" if target_pe else "- Target P/E: N/A",
        f"- Implied price: **{_fmt(implied_price)}**" if implied_price else "- Implied price: N/A",
        f"- Upside/downside: **{upside_pct:+.1%}**" if upside_pct else "- Upside/downside: N/A",
        "",
    ]

    # Revision history
    if revision_entry["changes"]:
        lines.append("## Revisions This Update")
        lines.append("")
        for c in revision_entry["changes"]:
            lines.append(f"- {c}")
        lines.append("")

    # Action items
    lines.extend([
        "## Action Items",
        "",
        "- [ ] Review and adjust key driver assumptions",
        "- [ ] Cross-check estimates against consensus (if available)",
        "- [ ] Run thesis health check if estimates changed materially",
        "",
    ])

    md_content = "\n".join(lines)
    md_path = io.write_text("model_update.md", md_content)
    print(f"  Markdown → {md_path}")

    # --- Persist to DB ---
    if persist:
        try:
            r = httpx.post(
                f"{API_URL}/api/analysis/reports",
                json={
                    "ticker": ticker,
                    "report_type": "model_update",
                    "content": md_content,
                },
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            print(f"  Persisted to DB ✓")
        except Exception as exc:
            print(f"  WARN: persist failed → {exc}")

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update projections for ticker")
    parser.add_argument("ticker", help="Stock ticker (e.g. NVDA)")
    parser.add_argument("--persist", action="store_true", help="Also save report to DB")
    args = parser.parse_args()
    update(args.ticker, persist=args.persist)


if __name__ == "__main__":
    main()
