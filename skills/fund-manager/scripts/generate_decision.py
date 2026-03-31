#!/usr/bin/env python3
"""Task 3 — Generate final trading decisions from debate artifacts.

Reads the debates JSON and produces actionable decision recommendations.
This script generates the *data-driven* decision template — the AI agent
fills in qualitative reasoning through the interactive CLI or direct editing.

Adapted from TradingAgents' Trader → Risk Judge → Portfolio Manager pipeline.

Usage::

    uv run python skills/fund-manager/scripts/generate_decision.py
    uv run python skills/fund-manager/scripts/generate_decision.py --date 2026-03-31
    uv run python skills/fund-manager/scripts/generate_decision.py --persist
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")
TIMEOUT = 30


def _quantitative_action(debate: dict) -> dict:
    """Derive a quantitative action suggestion from signal data.

    Returns a preliminary recommendation based purely on data signals.
    The agent provides the final decision with qualitative overlay.
    """
    summary = debate.get("signal_summary", {})
    bull_pct = summary.get("bull_pct", 0)
    bear_pct = summary.get("bear_pct", 0)
    bias = summary.get("signal_bias", "mixed")

    # Position context
    bull_args = summary.get("bull_signals", [])
    bear_args = summary.get("bear_signals", [])

    # Simple scoring: net bull signals weighted
    net_score = len(bull_args) - len(bear_args)

    if net_score >= 3:
        action = "buy"
        confidence = "high"
        reasoning = f"Strong bullish signal alignment ({len(bull_args)} bull vs {len(bear_args)} bear)"
    elif net_score >= 1:
        action = "hold"
        confidence = "medium"
        reasoning = f"Mild bullish tilt ({len(bull_args)} bull vs {len(bear_args)} bear) — insufficient for action"
    elif net_score <= -3:
        action = "sell"
        confidence = "high"
        reasoning = f"Strong bearish signal alignment ({len(bear_args)} bear vs {len(bull_args)} bull)"
    elif net_score <= -1:
        action = "trim"
        confidence = "medium"
        reasoning = f"Mild bearish tilt ({len(bear_args)} bear vs {len(bull_args)} bull) — consider reducing"
    else:
        action = "hold"
        confidence = "low"
        reasoning = "Signals are evenly split — no clear directional signal"

    return {
        "preliminary_action": action,
        "confidence": confidence,
        "quantitative_reasoning": reasoning,
        "signal_bias": bias,
        "bull_count": len(bull_args),
        "bear_count": len(bear_args),
        "net_score": net_score,
    }


def _build_decision(ticker: str, debate: dict, portfolio_context: dict) -> dict:
    """Build a decision artifact for one ticker."""
    quant = _quantitative_action(debate)

    return {
        "ticker": ticker,
        "preliminary": quant,
        "signals": {
            "thesis_health": debate.get("signal_summary", {}).get("bull_pct"),
            "signal_bias": debate.get("signal_summary", {}).get("signal_bias"),
        },
        # Agent fills these after reviewing the debate:
        "final_action": None,       # buy / sell / hold / trim / add
        "position_sizing": None,    # e.g. "add 2% of portfolio" or "trim 50 shares"
        "reasoning": None,          # Qualitative reasoning chain
        "risk_adjusted": None,      # After risk debate: did risk change the decision?
        "time_horizon": None,       # immediate / this_week / this_month
        "stop_loss": None,          # Optional stop-loss level
        "catalyst_trigger": None,   # What event would change this decision?
    }


def generate(decision_date: date, persist: bool = False) -> bool:
    """Generate decisions from debate artifacts."""
    date_str = decision_date.isoformat()
    io = ArtifactIO("_portfolio", "decisions")

    debates_data = io.read_json(f"{date_str}_debates.json")
    if not debates_data:
        print(f"  ✗  No debates for {date_str}. Run generate_debate.py first.")
        return False

    debates = debates_data.get("debates", {})
    portfolio_context = debates_data.get("portfolio_context", {})
    portfolio_risk = debates_data.get("portfolio_risk")

    print(f"Generating decisions for {date_str} ({len(debates)} positions)...")

    decisions = []
    for ticker, debate in debates.items():
        decision = _build_decision(ticker, debate, portfolio_context)
        decisions.append(decision)

        action = decision["preliminary"]["preliminary_action"]
        conf = decision["preliminary"]["confidence"]
        print(f"  {ticker}: {action.upper()} ({conf} confidence)")

    # Portfolio-level summary
    actions = [d["preliminary"]["preliminary_action"] for d in decisions]
    output = {
        "decision_date": date_str,
        "portfolio_context": portfolio_context,
        "portfolio_risk_summary": {
            "portfolio_beta": portfolio_risk.get("portfolio_beta") if portfolio_risk else None,
            "portfolio_sharpe": portfolio_risk.get("sharpe_ratio") if portfolio_risk else None,
            "portfolio_var_95": portfolio_risk.get("var_95") if portfolio_risk else None,
            "max_drawdown": portfolio_risk.get("max_drawdown") if portfolio_risk else None,
        },
        "decisions": decisions,
        "summary": {
            "total_positions": len(decisions),
            "buy_count": actions.count("buy"),
            "sell_count": actions.count("sell"),
            "hold_count": actions.count("hold"),
            "trim_count": actions.count("trim"),
            "add_count": actions.count("add"),
        },
        "status": "preliminary",  # → "reviewed" after agent fills in final decisions
    }

    # Write JSON
    json_path = io.write_json(f"{date_str}_decisions.json", output)
    print(f"\n  ✓  Decisions written to {json_path}")

    # Generate markdown report
    md = _render_markdown(output, debates_data)
    md_path = io.write_text(f"{date_str}_decisions.md", md)
    print(f"  ✓  Report written to {md_path}")

    if persist:
        _persist_report(date_str, md)

    return True


def _render_markdown(output: dict, debates_data: dict) -> str:
    """Render the decision report as markdown."""
    date_str = output["decision_date"]
    lines = [
        f"# Fund Manager Decision Report — {date_str}",
        "",
        f"**Status:** {output['status'].upper()}",
        "",
        "---",
        "",
        "## Portfolio Context",
        "",
    ]

    ctx = output.get("portfolio_context", {})
    lines.append(f"- **Total Value:** ${ctx.get('total_value', 'N/A'):,.0f}" if ctx.get("total_value") else "- **Total Value:** N/A")
    lines.append(f"- **Cash:** ${ctx.get('cash', 'N/A'):,.0f} ({ctx.get('cash_pct', 0):.1%})" if ctx.get("cash") else "- **Cash:** N/A")
    lines.append(f"- **Positions:** {ctx.get('position_count', 0)}")
    lines.append("")

    risk = output.get("portfolio_risk_summary", {})
    if any(v is not None for v in risk.values()):
        lines.append("## Portfolio Risk")
        lines.append("")
        if risk.get("portfolio_beta") is not None:
            lines.append(f"- **Beta:** {risk['portfolio_beta']:.2f}")
        if risk.get("portfolio_sharpe") is not None:
            lines.append(f"- **Sharpe:** {risk['portfolio_sharpe']:.2f}")
        if risk.get("portfolio_var_95") is not None:
            lines.append(f"- **VaR (95%):** {risk['portfolio_var_95']:.2%}")
        if risk.get("max_drawdown") is not None:
            lines.append(f"- **Max Drawdown:** {risk['max_drawdown']:.2%}")
        lines.append("")

    # Decision summary table
    lines.append("## Decision Summary")
    lines.append("")
    summ = output.get("summary", {})
    lines.append(f"| Action | Count |")
    lines.append(f"|--------|-------|")
    for action in ["buy", "sell", "hold", "trim", "add"]:
        count = summ.get(f"{action}_count", 0)
        if count > 0:
            lines.append(f"| **{action.upper()}** | {count} |")
    lines.append("")

    # Per-ticker decisions
    lines.append("## Position Decisions")
    lines.append("")

    debates = debates_data.get("debates", {})
    for decision in output.get("decisions", []):
        ticker = decision["ticker"]
        prelim = decision.get("preliminary", {})
        debate = debates.get(ticker, {})
        summary = debate.get("signal_summary", {})

        action = prelim.get("preliminary_action", "?").upper()
        conf = prelim.get("confidence", "?")

        lines.append(f"### {ticker} — {action} ({conf} confidence)")
        lines.append("")
        lines.append(f"**Quantitative:** {prelim.get('quantitative_reasoning', 'N/A')}")
        lines.append("")

        # Bull signals
        if summary.get("bull_signals"):
            lines.append("**Bull Signals:**")
            for s in summary["bull_signals"]:
                lines.append(f"- 🟢 {s}")
            lines.append("")

        # Bear signals
        if summary.get("bear_signals"):
            lines.append("**Bear Signals:**")
            for s in summary["bear_signals"]:
                lines.append(f"- 🔴 {s}")
            lines.append("")

        # Neutral
        if summary.get("neutral_signals"):
            lines.append("**Neutral:**")
            for s in summary["neutral_signals"]:
                lines.append(f"- ⚪ {s}")
            lines.append("")

        # Final decision placeholder
        final = decision.get("final_action")
        if final:
            lines.append(f"**FINAL DECISION:** {final.upper()}")
            if decision.get("reasoning"):
                lines.append(f"**Reasoning:** {decision['reasoning']}")
            if decision.get("position_sizing"):
                lines.append(f"**Sizing:** {decision['position_sizing']}")
        else:
            lines.append("**FINAL DECISION:** _Pending agent review_")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Human-in-the-loop reminder
    lines.append("> **⚠ HUMAN-IN-THE-LOOP:** This report contains preliminary")
    lines.append("> recommendations. Review all decisions before executing any trades.")
    lines.append("> No trades should be auto-executed.")
    lines.append("")

    return "\n".join(lines)


def _persist_report(date_str: str, md: str) -> None:
    """Upsert the decision report to the database."""
    try:
        resp = httpx.post(
            f"{API_URL}/api/analysis/reports",
            json={
                "ticker": "_PORTFOLIO",
                "report_type": "fund_manager_decision",
                "title": f"Fund Manager Decision — {date_str}",
                "content_md": md,
                "generated_by": "fund-manager-skill",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            print(f"  ✓  Report persisted to database")
        else:
            print(f"  ⚠  Persist failed: {resp.status_code}")
    except httpx.HTTPError as e:
        print(f"  ⚠  Persist failed: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fund-manager decisions")
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Decision date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist report to database",
    )
    args = parser.parse_args()
    decision_date = date.fromisoformat(args.date)
    ok = generate(decision_date, persist=args.persist)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
