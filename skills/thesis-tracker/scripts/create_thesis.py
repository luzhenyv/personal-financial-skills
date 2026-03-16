"""Create an investment thesis for a company.

Writes thesis.json + initializes updates.json, health_checks.json, catalysts.json
in data/artifacts/{TICKER}/thesis/.

Usage:
    uv run python skills/thesis-tracker/scripts/create_thesis.py NVDA --interactive
    uv run python skills/thesis-tracker/scripts/create_thesis.py NVDA \\
        --position long \\
        --thesis "NVDA is the picks-and-shovels play for AI infrastructure"
    uv run python skills/thesis-tracker/scripts/create_thesis.py NVDA --from-profile
    uv run python skills/thesis-tracker/scripts/create_thesis.py NVDA --from-json thesis_data.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


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
        opps = data.get("opportunities", [])
        if opps:
            seeds["opportunities"] = opps

    risk_path = profile_dir / "risk_factors.json"
    if risk_path.exists():
        data = json.loads(risk_path.read_text())
        risks = data.get("risks", [])
        if risks:
            seeds["risk_factors"] = [r.get("description", str(r)) for r in risks[:5]]

    return seeds


def _interactive_create(ticker: str) -> dict:
    """Prompt user for all thesis fields interactively."""
    print(f"\n{'='*60}")
    print(f"  Create Investment Thesis — {ticker}")
    print(f"{'='*60}\n")

    # Check for profile seeds
    seeds = _load_profile_seeds(ticker)
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

    # Buy reasons
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

    # Assumptions
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

    # Sell conditions
    print("\nSell conditions (enter blank line to stop):")
    sell_conditions = []
    for i in range(1, 6):
        cond = input(f"  Condition {i}: ").strip()
        if not cond:
            break
        sell_conditions.append(cond)

    # Risks
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


def main():
    parser = argparse.ArgumentParser(description="Create an investment thesis")
    parser.add_argument("ticker", type=str, help="Ticker symbol (e.g. NVDA)")
    parser.add_argument("--position", type=str, default="long", choices=["long", "short"])
    parser.add_argument("--thesis", type=str, help="Core thesis statement")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--from-json", type=str, help="Path to JSON file with thesis data")
    parser.add_argument("--from-profile", action="store_true",
                        help="Seed buy reasons and risks from company-profile artifacts")
    args = parser.parse_args()

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
        parser.error("Provide --thesis, --interactive, --from-profile, or --from-json")
        return

    from src.analysis.thesis_tracker import create_thesis, generate_thesis_markdown

    result = create_thesis(ticker, **data)

    # Generate markdown report
    md = generate_thesis_markdown(ticker)
    md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
    md_path.write_text(md)

    print(f"\n✅ Thesis created for {ticker}")
    print(f"   thesis.json → data/artifacts/{ticker}/thesis/thesis.json")
    print(f"   Report → data/artifacts/{ticker}/thesis/thesis_{ticker}.md")


if __name__ == "__main__":
    main()
