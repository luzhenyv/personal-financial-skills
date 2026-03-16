"""Run a thesis health check for a company.

Computes objective score from financial data, appends to health_checks.json,
and regenerates the markdown report.

Usage:
    uv run python skills/thesis-tracker/scripts/health_check.py NVDA
    uv run python skills/thesis-tracker/scripts/health_check.py --all
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def compute_objective_score(ticker: str, assumptions: list[dict]) -> tuple[float, list[dict]]:
    """Compute objective health score from financial data.

    Returns:
        Tuple of (overall_objective_score, per_assumption_scores).
    """
    from src.analysis.company_profile import get_profile_data

    profile = get_profile_data(ticker, years=3)
    if "error" in profile:
        return 50.0, []

    latest_metrics = (profile.get("metrics") or [{}])[-1]

    kpi_values = {
        "gross_margin": float(latest_metrics.get("gross_margin") or 0),
        "operating_margin": float(latest_metrics.get("operating_margin") or 0),
        "net_margin": float(latest_metrics.get("net_margin") or 0),
        "revenue_growth": float(latest_metrics.get("revenue_growth") or 0),
        "roe": float(latest_metrics.get("roe") or 0),
        "roic": float(latest_metrics.get("roic") or 0),
        "debt_to_equity": float(latest_metrics.get("debt_to_equity") or 0),
        "pe_ratio": float(latest_metrics.get("pe_ratio") or 0),
    }

    per_assumption = []
    weighted_sum = 0.0
    total_weight = 0.0

    for i, assumption in enumerate(assumptions):
        if isinstance(assumption, str):
            per_assumption.append({"assumption_idx": i, "objective": 50.0})
            continue

        weight = float(assumption.get("weight", 0))
        kpi_metric = assumption.get("kpi_metric")
        thresholds = assumption.get("kpi_thresholds")

        if kpi_metric and kpi_metric in kpi_values and thresholds:
            value = kpi_values[kpi_metric]
            score = _score_from_thresholds(value, thresholds)
        else:
            score = 50.0

        per_assumption.append({"assumption_idx": i, "objective": round(score, 1)})
        weighted_sum += score * weight
        total_weight += weight

    overall = weighted_sum / total_weight if total_weight > 0 else 50.0
    return round(overall, 2), per_assumption


def _score_from_thresholds(value: float, thresholds: dict) -> float:
    """Score a KPI value against threshold ranges (0-100)."""
    if not thresholds:
        return 50.0

    excellent = thresholds.get("excellent", float("inf"))
    good = thresholds.get("good", float("inf"))
    warning = thresholds.get("warning", float("-inf"))
    critical = thresholds.get("critical", float("-inf"))

    if value >= excellent:
        return 100.0
    elif value >= good:
        return 80.0
    elif value >= warning:
        return 50.0
    elif value >= critical:
        return 25.0
    else:
        return 10.0


def run_health_check(ticker: str) -> dict:
    """Run a full health check for *ticker* and return the result dict."""
    from src.analysis.thesis_tracker import get_active_thesis, add_health_check

    thesis = get_active_thesis(ticker)
    if thesis is None:
        print(f"❌ No active thesis found for {ticker}")
        sys.exit(1)

    assumptions = thesis.get("assumptions", [])
    obj_score, per_assumption = compute_objective_score(ticker, assumptions)

    # Subjective score: 50 = neutral placeholder for CLI usage
    subj_score = 50.0

    obj_w = 0.60
    subj_w = 0.40

    assumption_scores = []
    for i, a in enumerate(assumptions):
        obj_a = per_assumption[i]["objective"] if i < len(per_assumption) else 50.0
        subj_a = 50.0
        combined = obj_a * obj_w + subj_a * subj_w

        if combined >= 70:
            status = "✓ Intact"
        elif combined >= 40:
            status = "⚠️ Watch"
        else:
            status = "✗ Broken"

        desc = a.get("description", f"Assumption {i+1}") if isinstance(a, dict) else str(a)
        weight = a.get("weight") if isinstance(a, dict) else None

        assumption_scores.append({
            "assumption_idx": i,
            "description": desc,
            "weight": weight,
            "objective": round(obj_a, 1),
            "subjective": round(subj_a, 1),
            "combined": round(combined, 1),
            "status": status,
        })

    composite = obj_score * obj_w + subj_score * subj_w

    if composite >= 75:
        recommendation = "hold"
        reasoning = "Thesis remains strong. Continue monitoring assumptions."
    elif composite >= 50:
        recommendation = "hold"
        reasoning = "Thesis intact but showing some pressure. Watch closely."
    elif composite >= 30:
        recommendation = "trim"
        reasoning = "Thesis weakening materially. Consider reducing position size."
    else:
        recommendation = "exit"
        reasoning = "Multiple assumptions broken. Thesis no longer valid."

    observations = []
    for i, score in enumerate(assumption_scores):
        if score["combined"] < 40:
            observations.append(f"⚠️ {score['description']} — score {score['combined']:.0f}, below threshold")
        elif score["combined"] >= 80:
            observations.append(f"✓ {score['description']} — strong at {score['combined']:.0f}")

    result = add_health_check(
        ticker,
        check_date=str(date.today()),
        objective_score=obj_score,
        subjective_score=subj_score,
        assumption_scores=assumption_scores,
        key_observations=observations,
        recommendation=recommendation,
        recommendation_reasoning=reasoning,
    )

    return result


def main():
    parser = argparse.ArgumentParser(description="Run thesis health check")
    parser.add_argument("ticker", nargs="?", type=str, help="Ticker symbol")
    parser.add_argument("--all", action="store_true", help="Check all active theses")
    args = parser.parse_args()

    from src.analysis.thesis_tracker import generate_thesis_markdown

    if args.all:
        from src.analysis.thesis_tracker import get_all_active_theses
        theses = get_all_active_theses()
        if not theses:
            print("No active theses found.")
            return
        for t in theses:
            ticker = t["ticker"]
            print(f"\n--- {ticker} ---")
            result = run_health_check(ticker)
            # Regenerate markdown
            md = generate_thesis_markdown(ticker)
            Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md").write_text(md)

            print(f"  Composite: {result['composite_score']}/100")
            print(f"  Objective: {result['objective_score']} | Subjective: {result['subjective_score']}")
            print(f"  Recommendation: {result['recommendation']}")
    elif args.ticker:
        ticker = args.ticker.upper()
        result = run_health_check(ticker)

        md = generate_thesis_markdown(ticker)
        md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
        md_path.write_text(md)

        print(f"\n✅ Health check for {ticker}")
        print(f"   Composite: {result['composite_score']}/100")
        print(f"   Objective: {result['objective_score']} | Subjective: {result['subjective_score']}")
        print(f"   Recommendation: {result['recommendation']}")
        print(f"   Report → {md_path}")
    else:
        parser.error("Provide a ticker or --all")


if __name__ == "__main__":
    main()
