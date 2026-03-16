"""Manage the catalyst calendar for a thesis.

Usage:
    uv run python skills/thesis-tracker/scripts/manage_catalysts.py NVDA --list
    uv run python skills/thesis-tracker/scripts/manage_catalysts.py NVDA \\
        --add --event "Q4 FY2026 Earnings" --date 2026-02-26 --impact positive
    uv run python skills/thesis-tracker/scripts/manage_catalysts.py NVDA \\
        --resolve 1 --outcome "Beat on revenue and EPS"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def main():
    parser = argparse.ArgumentParser(description="Manage thesis catalyst calendar")
    parser.add_argument("ticker", type=str, help="Ticker symbol (e.g. NVDA)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all catalysts")
    group.add_argument("--add", action="store_true", help="Add a new catalyst")
    group.add_argument("--resolve", type=int, metavar="ID", help="Resolve a catalyst by ID")

    # --add options
    parser.add_argument("--event", type=str, help="Catalyst event name")
    parser.add_argument("--date", type=str, help="Expected date (YYYY-MM-DD)")
    parser.add_argument("--impact", type=str, default="neutral",
                        choices=["positive", "negative", "neutral"],
                        help="Expected impact on thesis")
    parser.add_argument("--assumptions", type=str,
                        help="Comma-separated assumption indices affected (e.g. 0,1)")
    parser.add_argument("--notes", type=str, default="", help="Additional notes")

    # --resolve options
    parser.add_argument("--outcome", type=str, default="", help="Outcome description")
    parser.add_argument("--status", type=str, default="resolved",
                        choices=["resolved", "expired", "postponed"])

    args = parser.parse_args()
    ticker = args.ticker.upper()

    from src.analysis.thesis_tracker import (
        get_catalysts, add_catalyst, update_catalyst, generate_thesis_markdown,
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
            parser.error("--add requires --event and --date")
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

        # Regenerate markdown
        md = generate_thesis_markdown(ticker)
        md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md)

        print(f"✅ Catalyst added (id={result['id']}): {result['event']}")
        print(f"   Report → {md_path}")

    elif args.resolve is not None:
        result = update_catalyst(
            ticker,
            args.resolve,
            status=args.status,
            outcome=args.outcome,
        )

        md = generate_thesis_markdown(ticker)
        md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
        md_path.write_text(md)

        print(f"✅ Catalyst {args.resolve} marked as {args.status}")
        print(f"   Report → {md_path}")


if __name__ == "__main__":
    main()
