"""Unified CLI for the thesis-tracker skill.

One entry point with subcommands: create, update, check, catalyst, report.

Usage:
    uv run python skills/thesis-tracker/scripts/thesis_cli.py create NVDA --interactive
    uv run python skills/thesis-tracker/scripts/thesis_cli.py create NVDA --from-profile
    uv run python skills/thesis-tracker/scripts/thesis_cli.py create NVDA --from-json data.json
    uv run python skills/thesis-tracker/scripts/thesis_cli.py create NVDA --thesis "Core thesis"

    uv run python skills/thesis-tracker/scripts/thesis_cli.py update NVDA --interactive
    uv run python skills/thesis-tracker/scripts/thesis_cli.py update NVDA --event "Q3 beat"

    uv run python skills/thesis-tracker/scripts/thesis_cli.py check NVDA
    uv run python skills/thesis-tracker/scripts/thesis_cli.py check --all

    uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst NVDA --list
    uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst NVDA --add --event "Q4 Earnings" --date 2026-02-26
    uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst NVDA --resolve 1

    uv run python skills/thesis-tracker/scripts/thesis_cli.py report NVDA
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Add project root and current script directory to path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _SCRIPT_DIR)


# ── Shared helpers ───────────────────────────────────────────────────────────


def _regenerate_report(ticker: str) -> Path:
    """Regenerate the markdown report and return its path."""
    from thesis_io import generate_thesis_markdown

    md = generate_thesis_markdown(ticker)
    md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md)
    return md_path


def _load_profile_seeds(ticker: str) -> dict:
    """Load buy reasons and risks from company-profile artifacts if available."""
    profile_dir = Path(f"data/artifacts/{ticker}/profile")
    seeds: dict = {}

    thesis_path = profile_dir / "investment_thesis.json"
    if thesis_path.exists():
        data = json.loads(thesis_path.read_text())
        bull = data.get("bull_case", [])
        if bull:
            seeds["buy_reasons"] = [
                {"title": b.get("title", ""), "description": b.get("description", "")}
                for b in bull[:5]
            ]

    risk_path = profile_dir / "risk_factors.json"
    if risk_path.exists():
        data = json.loads(risk_path.read_text())
        risks = data.get("risks", [])
        if risks:
            seeds["risk_factors"] = [r.get("description", str(r)) for r in risks[:5]]

    return seeds


# ── Subcommand: create ───────────────────────────────────────────────────────


def _interactive_create(ticker: str) -> dict:
    """Prompt user for all thesis fields interactively."""
    print(f"\n{'='*60}")
    print(f"  Create Investment Thesis — {ticker}")
    print(f"{'='*60}\n")

    seeds = _load_profile_seeds(ticker)
    use_seeds = "n"
    if seeds:
        print(f"  Found company-profile artifacts for {ticker}.")
        use_seeds = input("  Seed from profile data? (y/n) [y]: ").strip().lower() or "y"
        if use_seeds == "y":
            if seeds.get("buy_reasons"):
                print(f"  → {len(seeds['buy_reasons'])} buy reasons loaded from profile")
            if seeds.get("risk_factors"):
                print(f"  → {len(seeds['risk_factors'])} risk factors loaded from profile")
            print()

    position = input("Position (long/short) [long]: ").strip().lower() or "long"
    core_thesis = input("Core thesis (1-2 sentences): ").strip()

    buy_reasons = []
    if seeds.get("buy_reasons") and use_seeds == "y":
        buy_reasons = seeds["buy_reasons"]
        print(f"\nSeeded {len(buy_reasons)} buy reasons from profile. Add more or press Enter to continue:")
    else:
        print("\nBuy reasons (enter blank line to stop):")

    for i in range(len(buy_reasons) + 1, 6):
        title = input(f"  Reason {i} title: ").strip()
        if not title:
            break
        desc = input(f"  Reason {i} description: ").strip()
        buy_reasons.append({"title": title, "description": desc})

    print("\nPrerequisite assumptions with weights (must sum to 100%):")
    assumptions = []
    for i in range(1, 6):
        desc = input(f"  Assumption {i} description: ").strip()
        if not desc:
            break
        weight = float(input(f"  Assumption {i} weight (%): ").strip() or "0") / 100
        kpi_metric = input(f"  Assumption {i} KPI metric (e.g., gross_margin): ").strip()
        assumptions.append({
            "description": desc,
            "weight": weight,
            "kpi_metric": kpi_metric or None,
            "kpi_thresholds": None,
        })

    print("\nSell conditions (enter blank line to stop):")
    sell_conditions = []
    for i in range(1, 6):
        cond = input(f"  Condition {i}: ").strip()
        if not cond:
            break
        sell_conditions.append(cond)

    risk_factors = []
    if seeds.get("risk_factors") and use_seeds == "y":
        risk_factors = seeds["risk_factors"]
        print(f"\nSeeded {len(risk_factors)} risks from profile. Add more or press Enter to continue:")
    else:
        print("\nWhere I might be wrong (enter blank line to stop):")

    for i in range(len(risk_factors) + 1, 6):
        risk = input(f"  Risk {i}: ").strip()
        if not risk:
            break
        risk_factors.append(risk)

    target_str = input("\nTarget price (optional, press Enter to skip): ").strip()
    stop_str = input("Stop-loss price (optional, press Enter to skip): ").strip()

    return {
        "position": position,
        "core_thesis": core_thesis,
        "buy_reasons": buy_reasons,
        "assumptions": assumptions,
        "sell_conditions": sell_conditions,
        "risk_factors": risk_factors,
        "target_price": float(target_str) if target_str else None,
        "stop_loss_price": float(stop_str) if stop_str else None,
    }


def _normalize_weights(assumptions: list[dict]) -> list[dict]:
    """Ensure assumption weights sum to 1.0, auto-normalizing if needed."""
    if not assumptions:
        return assumptions
    total = sum(float(a.get("weight", 0)) for a in assumptions if isinstance(a, dict))
    if total == 0:
        # Equal weights if none specified
        even = round(1.0 / len(assumptions), 4)
        for a in assumptions:
            if isinstance(a, dict):
                a["weight"] = even
    elif abs(total - 1.0) > 0.001:
        print(f"  ⚠️  Weights sum to {total:.1%}, auto-normalizing to 100%")
        for a in assumptions:
            if isinstance(a, dict) and a.get("weight"):
                a["weight"] = round(float(a["weight"]) / total, 4)
    return assumptions


def cmd_create(args: argparse.Namespace) -> None:
    ticker = args.ticker.upper()

    if args.from_json:
        data = json.loads(Path(args.from_json).read_text())
    elif args.from_profile:
        seeds = _load_profile_seeds(ticker)
        if not seeds:
            print(f"No company-profile artifacts found for {ticker}.")
            print(f"Run: uv run python skills/company-profile/scripts/generate_report.py {ticker}")
            sys.exit(1)
        data = {
            "position": args.position,
            "core_thesis": args.thesis or "",
            "buy_reasons": seeds.get("buy_reasons", []),
            "assumptions": [],
            "sell_conditions": [],
            "risk_factors": seeds.get("risk_factors", []),
        }
        if not data["core_thesis"]:
            print("Warning: --thesis not provided. Core thesis will be empty.")
    elif args.interactive:
        data = _interactive_create(ticker)
    elif args.thesis:
        data = {
            "position": args.position,
            "core_thesis": args.thesis,
            "buy_reasons": [],
            "assumptions": [],
            "sell_conditions": [],
            "risk_factors": [],
        }
    else:
        print("Error: provide --thesis, --interactive, --from-profile, or --from-json")
        sys.exit(1)

    if data.get("assumptions"):
        data["assumptions"] = _normalize_weights(data["assumptions"])

    from thesis_io import create_thesis

    create_thesis(ticker, **data)
    md_path = _regenerate_report(ticker)

    print(f"\n✅ Thesis created for {ticker}")
    print(f"   thesis.json → data/artifacts/{ticker}/thesis/thesis.json")
    print(f"   Report → {md_path}")


# ── Subcommand: update ──────────────────────────────────────────────────────


def _interactive_update(ticker: str) -> dict:
    from thesis_io import get_active_thesis

    thesis = get_active_thesis(ticker)
    if thesis is None:
        print(f"❌ No active thesis found for {ticker}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Update Thesis — {ticker}")
    print(f"  Core thesis: {thesis['core_thesis']}")
    print(f"{'='*60}\n")

    event_date_str = input(f"Event date [today={date.today()}]: ").strip()
    event_date = event_date_str if event_date_str else str(date.today())
    event_title = input("Event title: ").strip()
    event_description = input("Event description: ").strip()

    assumptions = thesis.get("assumptions", [])
    impacts = {}
    if assumptions:
        print("\nAssumption impacts (✓ strengthened, ⚠️ weakened, ✗ broken, — no change):")
        for i, a in enumerate(assumptions):
            desc = a.get("description", f"Assumption {i+1}") if isinstance(a, dict) else str(a)
            status = input(f"  {desc} [—]: ").strip() or "—"
            explanation = input(f"    Explanation: ").strip()
            impacts[str(i)] = {"status": status, "explanation": explanation}

    strength = input("Thesis strength change (strengthened/weakened/unchanged) [unchanged]: ").strip() or "unchanged"
    action = input("Action (hold/add/trim/exit) [hold]: ").strip() or "hold"
    conviction = input("Conviction (high/medium/low) [medium]: ").strip() or "medium"
    notes = input("Notes (optional): ").strip()

    return {
        "event_date": event_date,
        "event_title": event_title,
        "event_description": event_description or None,
        "assumption_impacts": impacts,
        "strength_change": strength,
        "action_taken": action,
        "conviction": conviction,
        "notes": notes or None,
    }


def cmd_update(args: argparse.Namespace) -> None:
    ticker = args.ticker.upper()

    if args.interactive:
        data = _interactive_update(ticker)
    elif args.event:
        data = {
            "event_date": str(date.today()),
            "event_title": args.event,
            "strength_change": args.strength,
            "action_taken": args.action,
            "conviction": args.conviction,
        }
    else:
        print("Error: provide --event or --interactive")
        sys.exit(1)

    from thesis_io import add_thesis_update

    result = add_thesis_update(ticker, **data)
    md_path = _regenerate_report(ticker)

    print(f"\n✅ Thesis update recorded for {ticker}")
    print(f"   Strength: {result['strength_change']} → Action: {result['action_taken']}")
    print(f"   Report → {md_path}")


# ── Subcommand: check ────────────────────────────────────────────────────────


def _compute_objective_score(ticker: str, assumptions: list[dict]) -> tuple[float, list[dict]]:
    """Compute objective health score from financial data."""
    import os
    import httpx
    _API_BASE = os.environ.get("PFS_API_URL", "http://127.0.0.1:8000")
    r = httpx.get(f"{_API_BASE}/api/analysis/profile/{ticker}", params={"years": 3}, timeout=60)
    r.raise_for_status()
    profile = r.json()
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


def _run_health_check(ticker: str) -> dict:
    """Run a full health check for *ticker* and return the result dict."""
    from thesis_io import get_active_thesis, add_health_check

    thesis = get_active_thesis(ticker)
    if thesis is None:
        print(f"❌ No active thesis found for {ticker}")
        sys.exit(1)

    assumptions = thesis.get("assumptions", [])
    obj_score, per_assumption = _compute_objective_score(ticker, assumptions)

    # Subjective score: 50 = neutral placeholder for CLI usage.
    # The agent provides real subjective scores when running via SKILL workflow.
    subj_score = 50.0

    obj_w, subj_w = 0.60, 0.40

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
        recommendation, reasoning = "hold", "Thesis remains strong. Continue monitoring assumptions."
    elif composite >= 50:
        recommendation, reasoning = "hold", "Thesis intact but showing some pressure. Watch closely."
    elif composite >= 30:
        recommendation, reasoning = "trim", "Thesis weakening materially. Consider reducing position size."
    else:
        recommendation, reasoning = "exit", "Multiple assumptions broken. Thesis no longer valid."

    observations = []
    for score in assumption_scores:
        if score["combined"] < 40:
            observations.append(f"⚠️ {score['description']} — score {score['combined']:.0f}, below threshold")
        elif score["combined"] >= 80:
            observations.append(f"✓ {score['description']} — strong at {score['combined']:.0f}")

    return add_health_check(
        ticker,
        check_date=str(date.today()),
        objective_score=obj_score,
        subjective_score=subj_score,
        assumption_scores=assumption_scores,
        key_observations=observations,
        recommendation=recommendation,
        recommendation_reasoning=reasoning,
    )


def cmd_check(args: argparse.Namespace) -> None:
    if args.all:
        from thesis_io import get_all_active_theses

        theses = get_all_active_theses()
        if not theses:
            print("No active theses found.")
            return
        for t in theses:
            ticker = t["ticker"]
            print(f"\n--- {ticker} ---")
            result = _run_health_check(ticker)
            _regenerate_report(ticker)
            print(f"  Composite: {result['composite_score']}/100")
            print(f"  Objective: {result['objective_score']} | Subjective: {result['subjective_score']}")
            print(f"  Recommendation: {result['recommendation']}")
    elif args.ticker:
        ticker = args.ticker.upper()
        result = _run_health_check(ticker)
        md_path = _regenerate_report(ticker)
        print(f"\n✅ Health check for {ticker}")
        print(f"   Composite: {result['composite_score']}/100")
        print(f"   Objective: {result['objective_score']} | Subjective: {result['subjective_score']}")
        print(f"   Recommendation: {result['recommendation']}")
        print(f"   Report → {md_path}")
    else:
        print("Error: provide a ticker or --all")
        sys.exit(1)


# ── Subcommand: catalyst ─────────────────────────────────────────────────────


def cmd_catalyst(args: argparse.Namespace) -> None:
    ticker = args.ticker.upper()

    from thesis_io import (
        get_catalysts, add_catalyst, update_catalyst,
    )

    if args.list:
        catalysts = get_catalysts(ticker)
        if not catalysts:
            print(f"No catalysts for {ticker}.")
            return
        pending = [c for c in catalysts if c.get("status") == "pending"]
        resolved = [c for c in catalysts if c.get("status") != "pending"]

        if pending:
            print(f"\n📅 Pending Catalysts — {ticker}")
            print(f"{'ID':>4}  {'Date':<12} {'Impact':<10} Event")
            print(f"{'─'*4}  {'─'*12} {'─'*10} {'─'*30}")
            for c in pending:
                print(f"{c['id']:>4}  {c['expected_date']:<12} {c['expected_impact']:<10} {c['event']}")

        if resolved:
            print(f"\n✅ Resolved Catalysts — {ticker}")
            for c in resolved:
                print(f"  [{c['id']}] {c['event']} — {c.get('outcome', 'N/A')}")

    elif args.add:
        if not args.event or not args.date:
            print("Error: --add requires --event and --date")
            sys.exit(1)
        affected = []
        if args.assumptions:
            affected = [int(x.strip()) for x in args.assumptions.split(",")]

        result = add_catalyst(
            ticker,
            event=args.event,
            expected_date=args.date,
            expected_impact=args.impact,
            affected_assumptions=affected,
            notes=args.notes,
        )
        md_path = _regenerate_report(ticker)
        print(f"✅ Catalyst added (id={result['id']}): {result['event']}")
        print(f"   Report → {md_path}")

    elif args.resolve is not None:
        result = update_catalyst(
            ticker, args.resolve,
            status=args.status,
            outcome=args.outcome,
        )
        md_path = _regenerate_report(ticker)
        print(f"✅ Catalyst {args.resolve} marked as {args.status}")
        print(f"   Report → {md_path}")

    else:
        print("Error: provide --list, --add, or --resolve ID")
        sys.exit(1)


# ── Subcommand: report ───────────────────────────────────────────────────────


def cmd_report(args: argparse.Namespace) -> None:
    ticker = args.ticker.upper()

    from thesis_io import generate_thesis_markdown

    md = generate_thesis_markdown(ticker)
    if not md:
        print(f"❌ No thesis found for {ticker}")
        print(f"   Create one first: uv run python skills/thesis-tracker/scripts/thesis_cli.py create {ticker} -i")
        sys.exit(1)

    md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md)
    print(f"✅ Report generated → {md_path}")


# ── Argument parser ──────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thesis_cli",
        description="Unified CLI for thesis-tracker skill",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- create --
    p_create = sub.add_parser("create", help="Create an investment thesis")
    p_create.add_argument("ticker", type=str, help="Ticker symbol")
    p_create.add_argument("--position", type=str, default="long", choices=["long", "short"])
    p_create.add_argument("--thesis", type=str, help="Core thesis statement")
    p_create.add_argument("--interactive", "-i", action="store_true")
    p_create.add_argument("--from-json", type=str, help="Path to JSON file with thesis data")
    p_create.add_argument("--from-profile", action="store_true",
                          help="Seed from company-profile artifacts")

    # -- update --
    p_update = sub.add_parser("update", help="Log a thesis update")
    p_update.add_argument("ticker", type=str, help="Ticker symbol")
    p_update.add_argument("--event", type=str, help="Event title")
    p_update.add_argument("--strength", type=str, default="unchanged",
                          choices=["strengthened", "weakened", "unchanged"])
    p_update.add_argument("--action", type=str, default="hold",
                          choices=["hold", "add", "trim", "exit"])
    p_update.add_argument("--conviction", type=str, default="medium",
                          choices=["high", "medium", "low"])
    p_update.add_argument("--interactive", "-i", action="store_true")

    # -- check --
    p_check = sub.add_parser("check", help="Run a thesis health check")
    p_check.add_argument("ticker", nargs="?", type=str, help="Ticker symbol")
    p_check.add_argument("--all", action="store_true", help="Check all active theses")

    # -- catalyst --
    p_cat = sub.add_parser("catalyst", help="Manage catalyst calendar")
    p_cat.add_argument("ticker", type=str, help="Ticker symbol")
    cat_group = p_cat.add_mutually_exclusive_group(required=True)
    cat_group.add_argument("--list", action="store_true")
    cat_group.add_argument("--add", action="store_true")
    cat_group.add_argument("--resolve", type=int, metavar="ID")
    p_cat.add_argument("--event", type=str)
    p_cat.add_argument("--date", type=str)
    p_cat.add_argument("--impact", type=str, default="neutral",
                       choices=["positive", "negative", "neutral"])
    p_cat.add_argument("--assumptions", type=str, help="Comma-separated assumption indices")
    p_cat.add_argument("--notes", type=str, default="")
    p_cat.add_argument("--outcome", type=str, default="")
    p_cat.add_argument("--status", type=str, default="resolved",
                       choices=["resolved", "expired", "postponed"])

    # -- report --
    p_report = sub.add_parser("report", help="Regenerate the markdown report")
    p_report.add_argument("ticker", type=str, help="Ticker symbol")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "create": cmd_create,
        "update": cmd_update,
        "check": cmd_check,
        "catalyst": cmd_catalyst,
        "report": cmd_report,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
