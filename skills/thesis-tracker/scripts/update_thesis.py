"""Add an update entry to an existing thesis.

Appends to updates.json and regenerates the markdown report.

Usage:
    uv run python skills/thesis-tracker/scripts/update_thesis.py NVDA --interactive
    uv run python skills/thesis-tracker/scripts/update_thesis.py NVDA \\
        --event "Q3 2025 earnings beat" \\
        --strength strengthened \\
        --action hold \\
        --conviction high
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _interactive_update(ticker: str) -> dict:
    """Prompt user for update fields."""
    from src.analysis.thesis_tracker import get_active_thesis

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


def main():
    parser = argparse.ArgumentParser(description="Update an investment thesis")
    parser.add_argument("ticker", type=str, help="Ticker symbol")
    parser.add_argument("--event", type=str, help="Event title")
    parser.add_argument("--strength", type=str, default="unchanged",
                        choices=["strengthened", "weakened", "unchanged"])
    parser.add_argument("--action", type=str, default="hold",
                        choices=["hold", "add", "trim", "exit"])
    parser.add_argument("--conviction", type=str, default="medium",
                        choices=["high", "medium", "low"])
    parser.add_argument("--interactive", "-i", action="store_true")
    args = parser.parse_args()

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
        parser.error("Provide --event or --interactive")
        return

    from src.analysis.thesis_tracker import add_thesis_update, generate_thesis_markdown

    result = add_thesis_update(ticker, **data)

    # Regenerate markdown
    md = generate_thesis_markdown(ticker)
    md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
    md_path.write_text(md)

    print(f"\n✅ Thesis update recorded for {ticker}")
    print(f"   Strength: {result['strength_change']} → Action: {result['action_taken']}")
    print(f"   Report → {md_path}")


if __name__ == "__main__":
    main()
