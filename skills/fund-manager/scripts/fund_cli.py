#!/usr/bin/env python3
"""Fund Manager CLI — unified entry point for the fund-manager skill.

Merges TradingAgents' multi-agent pipeline into PFS's collect → generate
→ decide workflow with human-in-the-loop.

Usage::

    # Full pipeline (collect + debate + decide)
    uv run python skills/fund-manager/scripts/fund_cli.py run

    # Individual steps
    uv run python skills/fund-manager/scripts/fund_cli.py collect
    uv run python skills/fund-manager/scripts/fund_cli.py debate
    uv run python skills/fund-manager/scripts/fund_cli.py debate --ticker NVDA
    uv run python skills/fund-manager/scripts/fund_cli.py decide
    uv run python skills/fund-manager/scripts/fund_cli.py decide --persist

    # Review and finalize decisions interactively
    uv run python skills/fund-manager/scripts/fund_cli.py review
    uv run python skills/fund-manager/scripts/fund_cli.py review --ticker NVDA

    # View latest decisions
    uv run python skills/fund-manager/scripts/fund_cli.py show
    uv run python skills/fund-manager/scripts/fund_cli.py history
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO


def cmd_run(args: argparse.Namespace) -> int:
    """Run the full pipeline: collect → debate → decide."""
    from collect_signals import collect
    from generate_debate import generate as gen_debate
    from generate_decision import generate as gen_decision

    decision_date = date.fromisoformat(args.date)
    print("=" * 60)
    print(f"  FUND MANAGER — Full Pipeline — {decision_date}")
    print("=" * 60)

    print("\n── Phase 1: Signal Collection ──")
    if not collect(decision_date):
        print("\n✗ Signal collection failed.")
        return 1

    print("\n── Phase 2: Bull/Bear Debate ──")
    if not gen_debate(decision_date, ticker_filter=args.ticker):
        print("\n✗ Debate generation failed.")
        return 1

    print("\n── Phase 3: Decision Generation ──")
    if not gen_decision(decision_date, persist=args.persist):
        print("\n✗ Decision generation failed.")
        return 1

    print("\n" + "=" * 60)
    print("  ✓ Pipeline complete. Review decisions before trading.")
    print("=" * 60)
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    """Collect signals from all sources."""
    from collect_signals import collect

    decision_date = date.fromisoformat(args.date)
    return 0 if collect(decision_date) else 1


def cmd_debate(args: argparse.Namespace) -> int:
    """Generate bull/bear debate scaffolds."""
    from generate_debate import generate

    decision_date = date.fromisoformat(args.date)
    return 0 if generate(decision_date, ticker_filter=args.ticker) else 1


def cmd_decide(args: argparse.Namespace) -> int:
    """Generate preliminary decisions."""
    from generate_decision import generate

    decision_date = date.fromisoformat(args.date)
    return 0 if generate(decision_date, persist=args.persist) else 1


def cmd_review(args: argparse.Namespace) -> int:
    """Interactive review of decisions — fill in final actions."""
    decision_date = date.fromisoformat(args.date)
    date_str = decision_date.isoformat()
    io = ArtifactIO("_portfolio", "decisions")

    data = io.read_json(f"{date_str}_decisions.json")
    if not data:
        print(f"✗ No decisions for {date_str}. Run the pipeline first.")
        return 1

    decisions = data.get("decisions", [])
    ticker_filter = args.ticker.upper() if args.ticker else None

    print(f"\n  Fund Manager Review — {date_str}")
    print(f"  {len(decisions)} position(s)\n")

    modified = False
    for d in decisions:
        ticker = d["ticker"]
        if ticker_filter and ticker != ticker_filter:
            continue

        prelim = d.get("preliminary", {})
        print(f"  ── {ticker} ──")
        print(f"  Preliminary: {prelim.get('preliminary_action', '?').upper()} ({prelim.get('confidence', '?')})")
        print(f"  Reasoning: {prelim.get('quantitative_reasoning', 'N/A')}")

        if d.get("final_action"):
            print(f"  Current final: {d['final_action'].upper()}")

        print()
        action = input(f"  Final action for {ticker} [buy/sell/hold/trim/add/skip]: ").strip().lower()
        if action == "skip" or not action:
            continue

        if action not in ("buy", "sell", "hold", "trim", "add"):
            print(f"  ⚠ Invalid action: {action}")
            continue

        d["final_action"] = action

        reasoning = input(f"  Reasoning: ").strip()
        if reasoning:
            d["reasoning"] = reasoning

        sizing = input(f"  Position sizing (e.g. 'add 2%', 'trim 50 shares'): ").strip()
        if sizing:
            d["position_sizing"] = sizing

        horizon = input(f"  Time horizon [immediate/this_week/this_month]: ").strip()
        if horizon:
            d["time_horizon"] = horizon

        modified = True
        print(f"  ✓ {ticker}: {action.upper()}")
        print()

    if modified:
        data["status"] = "reviewed"
        io.write_json(f"{date_str}_decisions.json", data)
        print(f"\n✓ Decisions updated and saved.")
    else:
        print(f"\nNo changes made.")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show the latest decisions."""
    io = ArtifactIO("_portfolio", "decisions")

    # Find most recent decision file
    files = io.list_files("_decisions.json")
    if not files:
        print("No decision files found.")
        return 1

    latest = files[-1]
    data = io.read_json(latest)
    if not data:
        return 1

    date_str = data.get("decision_date", "?")
    status = data.get("status", "?")
    print(f"\n  Latest Decisions — {date_str} (status: {status})")
    print(f"  {'─' * 50}")

    for d in data.get("decisions", []):
        ticker = d["ticker"]
        prelim = d.get("preliminary", {})
        final = d.get("final_action")
        action = final or prelim.get("preliminary_action", "?")
        conf = prelim.get("confidence", "?")
        status_str = "FINAL" if final else "PRELIM"
        print(f"  {ticker:6s}  {action.upper():6s}  ({conf}) [{status_str}]")

    summary = data.get("summary", {})
    print(f"\n  Total: {summary.get('total_positions', 0)} positions")
    print(f"  Buy: {summary.get('buy_count', 0)} | Sell: {summary.get('sell_count', 0)} | Hold: {summary.get('hold_count', 0)} | Trim: {summary.get('trim_count', 0)}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """List all decision dates."""
    io = ArtifactIO("_portfolio", "decisions")
    files = io.list_files("_decisions.json")
    if not files:
        print("No decision history found.")
        return 1

    print("\n  Decision History")
    print(f"  {'─' * 40}")
    for f in files:
        data = io.read_json(f)
        if data:
            d = data.get("decision_date", "?")
            s = data.get("status", "?")
            n = len(data.get("decisions", []))
            print(f"  {d}  {s:12s}  {n} positions")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fund_cli",
        description="Fund Manager — TradingAgents-inspired decision engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Shared args
    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--date", default=date.today().isoformat(), help="Decision date")

    # run
    p_run = sub.add_parser("run", help="Full pipeline: collect → debate → decide")
    add_common(p_run)
    p_run.add_argument("--ticker", default=None, help="Filter to single ticker")
    p_run.add_argument("--persist", action="store_true", help="Persist report to DB")
    p_run.set_defaults(func=cmd_run)

    # collect
    p_collect = sub.add_parser("collect", help="Collect signals from all sources")
    add_common(p_collect)
    p_collect.set_defaults(func=cmd_collect)

    # debate
    p_debate = sub.add_parser("debate", help="Generate bull/bear debate scaffolds")
    add_common(p_debate)
    p_debate.add_argument("--ticker", default=None, help="Filter to single ticker")
    p_debate.set_defaults(func=cmd_debate)

    # decide
    p_decide = sub.add_parser("decide", help="Generate preliminary decisions")
    add_common(p_decide)
    p_decide.add_argument("--persist", action="store_true", help="Persist to DB")
    p_decide.set_defaults(func=cmd_decide)

    # review
    p_review = sub.add_parser("review", help="Interactive decision review")
    add_common(p_review)
    p_review.add_argument("--ticker", default=None, help="Review single ticker")
    p_review.set_defaults(func=cmd_review)

    # show
    p_show = sub.add_parser("show", help="Show latest decisions")
    p_show.set_defaults(func=cmd_show)

    # history
    p_hist = sub.add_parser("history", help="List decision history")
    p_hist.set_defaults(func=cmd_history)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
