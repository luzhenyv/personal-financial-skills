"""Create an investment thesis for a company.

Usage:
    uv run python skills/thesis-tracker/scripts/create_thesis.py NVDA --interactive
    uv run python skills/thesis-tracker/scripts/create_thesis.py NVDA \\
        --position long \\
        --thesis "NVDA is the picks-and-shovels play for AI infrastructure"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _interactive_create(ticker: str) -> dict:
    """Prompt user for all thesis fields interactively."""
    print(f"\n{'='*60}")
    print(f"  Create Investment Thesis — {ticker}")
    print(f"{'='*60}\n")

    position = input("Position (long/short) [long]: ").strip().lower() or "long"
    core_thesis = input("Core thesis (1-2 sentences): ").strip()

    print("\nBuy reasons (enter blank line to stop):")
    buy_reasons = []
    for i in range(1, 6):
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

    print("\nWhere I might be wrong (enter blank line to stop):")
    risk_factors = []
    for i in range(1, 6):
        risk = input(f"  Risk {i}: ").strip()
        if not risk:
            break
        risk_factors.append({"description": risk})

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
    args = parser.parse_args()

    ticker = args.ticker.upper()

    if args.from_json:
        data = json.loads(Path(args.from_json).read_text())
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
        parser.error("Provide --thesis, --interactive, or --from-json")
        return

    from src.analysis.thesis_tracker import create_thesis

    result = create_thesis(ticker, **data)
    print(f"\n✅ Thesis created for {ticker} (id={result['id']})")
    print(f"   File: data/processed/{ticker}/thesis_{ticker}.md")


if __name__ == "__main__":
    main()
