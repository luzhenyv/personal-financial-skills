#!/usr/bin/env python3
"""Task 2 — Generate bull/bear debate + risk assessment from signals.

Reads the signals JSON from Task 1 and structures both:
  - Bull vs Bear investment debate per ticker
  - Risk assessment with aggressive/conservative/neutral perspectives

Adapted from TradingAgents' multi-agent debate pattern:
  - Bull Researcher → Bear Researcher → Research Manager (judge)
  - Aggressive → Conservative → Neutral → Risk Judge

In PFS, we don't run LLM agents here — we structure the data for the
AI agent to fill in during the interactive decision session. The script
produces a *debate scaffold* that the agent completes.

Usage::

    uv run python skills/fund-manager/scripts/generate_debate.py
    uv run python skills/fund-manager/scripts/generate_debate.py --date 2026-03-31
    uv run python skills/fund-manager/scripts/generate_debate.py --ticker NVDA
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import ArtifactIO


def _classify_signal(value: float | None, thresholds: dict) -> str:
    """Classify a numeric signal into bullish/neutral/bearish."""
    if value is None:
        return "neutral"
    if value > thresholds.get("bullish", 0):
        return "bullish"
    if value < thresholds.get("bearish", 0):
        return "bearish"
    return "neutral"


def _build_signal_summary(ticker: str, signals: dict) -> dict:
    """Summarize signals into bullish/bearish/neutral categories."""
    bull_signals = []
    bear_signals = []
    neutral_signals = []

    # ── Technical indicators (TradingAgents Market Analyst style) ──
    market = signals.get("market", {})
    technicals = market.get("technicals", {})
    tech_signals = technicals.get("signals", {})
    ma = technicals.get("moving_averages", {})
    macd = technicals.get("macd", {})
    rsi = technicals.get("rsi")
    bb = technicals.get("bollinger_bands", {})
    atr = technicals.get("atr")
    vwma = technicals.get("vwma")

    # Moving averages
    if tech_signals.get("golden_cross"):
        bull_signals.append("Golden cross (SMA50 > SMA200)")
    elif tech_signals.get("death_cross"):
        bear_signals.append("Death cross (SMA50 < SMA200)")

    sma50_pct = ma.get("price_vs_sma50_pct")
    if sma50_pct is not None:
        if sma50_pct > 0.02:
            bull_signals.append(f"Above SMA50 by {sma50_pct:.1%}")
        elif sma50_pct < -0.02:
            bear_signals.append(f"Below SMA50 by {sma50_pct:.1%}")

    sma200_pct = ma.get("price_vs_sma200_pct")
    if sma200_pct is not None:
        if sma200_pct > 0:
            bull_signals.append(f"Above SMA200 (long-term uptrend)")
        elif sma200_pct < 0:
            bear_signals.append(f"Below SMA200 (long-term downtrend)")

    ema10_pct = ma.get("price_vs_ema10_pct")
    if ema10_pct is not None:
        if ema10_pct > 0.01:
            bull_signals.append(f"Above EMA10 — short-term momentum positive")
        elif ema10_pct < -0.01:
            bear_signals.append(f"Below EMA10 — short-term momentum negative")

    # MACD
    if tech_signals.get("macd_bullish"):
        macd_val = macd.get("macd", 0)
        bull_signals.append(f"MACD bullish crossover (MACD={macd_val})")
    elif tech_signals.get("macd_bearish"):
        macd_val = macd.get("macd", 0)
        bear_signals.append(f"MACD bearish crossover (MACD={macd_val})")

    hist = macd.get("macd_histogram")
    if hist is not None:
        if hist > 0:
            bull_signals.append(f"MACD histogram positive ({hist:.4f}) — increasing momentum")
        else:
            bear_signals.append(f"MACD histogram negative ({hist:.4f}) — decreasing momentum")

    # RSI
    if rsi is not None:
        if rsi > 70:
            bear_signals.append(f"RSI overbought: {rsi:.1f} — reversal risk")
        elif rsi < 30:
            bull_signals.append(f"RSI oversold: {rsi:.1f} — potential bounce")
        elif rsi > 60:
            bull_signals.append(f"RSI bullish: {rsi:.1f}")
        elif rsi < 40:
            bear_signals.append(f"RSI bearish: {rsi:.1f}")
        else:
            neutral_signals.append(f"RSI neutral: {rsi:.1f}")

    # Bollinger Bands
    bb_pos = tech_signals.get("bb_position")
    bb_pct_b = bb.get("bb_pct_b")
    if bb_pos == "above_upper":
        bear_signals.append(f"Price above Bollinger upper band (%B={bb_pct_b:.2f}) — overextended")
    elif bb_pos == "below_lower":
        bull_signals.append(f"Price below Bollinger lower band (%B={bb_pct_b:.2f}) — oversold")

    bb_width = bb.get("bb_width")
    if bb_width is not None:
        if bb_width < 0.03:
            neutral_signals.append(f"Bollinger squeeze (width={bb_width:.4f}) — breakout imminent")
        elif bb_width > 0.10:
            neutral_signals.append(f"Bollinger expansion (width={bb_width:.4f}) — high volatility")

    # ATR
    if atr is not None:
        latest_price = market.get("latest_price")
        if latest_price and latest_price > 0:
            atr_pct = atr / latest_price
            if atr_pct > 0.03:
                bear_signals.append(f"High ATR: {atr:.2f} ({atr_pct:.1%} of price) — elevated volatility")
            else:
                neutral_signals.append(f"ATR: {atr:.2f} ({atr_pct:.1%} of price)")

    # VWMA
    if vwma is not None and tech_signals.get("above_vwma") is not None:
        if tech_signals["above_vwma"]:
            bull_signals.append(f"Price above VWMA ({vwma:.2f}) — volume-weighted trend bullish")
        else:
            bear_signals.append(f"Price below VWMA ({vwma:.2f}) — volume-weighted trend bearish")

    # ── Price momentum ──
    momentum = market.get("momentum", {})
    ret_20d = momentum.get("return_20d")
    if ret_20d is not None:
        if ret_20d > 0.05:
            bull_signals.append(f"Strong 20d return: +{ret_20d:.1%}")
        elif ret_20d < -0.05:
            bear_signals.append(f"Weak 20d return: {ret_20d:.1%}")

    ret_60d = momentum.get("return_60d")
    if ret_60d is not None:
        if ret_60d > 0.10:
            bull_signals.append(f"Strong 60d return: +{ret_60d:.1%}")
        elif ret_60d < -0.10:
            bear_signals.append(f"Weak 60d return: {ret_60d:.1%}")

    # Fundamentals
    fundamentals = signals.get("fundamentals", {}).get("metrics", {})
    rev_growth = fundamentals.get("revenue_growth")
    if rev_growth is not None:
        if rev_growth > 0.15:
            bull_signals.append(f"Strong revenue growth: {rev_growth:.1%}")
        elif rev_growth < 0:
            bear_signals.append(f"Revenue decline: {rev_growth:.1%}")

    gross_margin = fundamentals.get("gross_margin")
    if gross_margin is not None:
        if gross_margin > 0.50:
            bull_signals.append(f"High gross margin: {gross_margin:.1%}")
        elif gross_margin < 0.20:
            bear_signals.append(f"Low gross margin: {gross_margin:.1%}")

    roe = fundamentals.get("roe")
    if roe is not None:
        if roe > 0.20:
            bull_signals.append(f"Strong ROE: {roe:.1%}")
        elif roe < 0.05:
            bear_signals.append(f"Weak ROE: {roe:.1%}")

    pe = fundamentals.get("pe_ratio")
    if pe is not None:
        if pe > 40:
            bear_signals.append(f"High P/E: {pe:.1f}x — premium valuation risk")
        elif pe < 15 and pe > 0:
            bull_signals.append(f"Low P/E: {pe:.1f}x — potentially undervalued")

    # Thesis health
    thesis = signals.get("thesis", {})
    health_score = thesis.get("health_score")
    if health_score is not None:
        if health_score >= 70:
            bull_signals.append(f"Thesis health: {health_score}/100 ({thesis.get('health_grade', '?')})")
        elif health_score < 50:
            bear_signals.append(f"Weak thesis health: {health_score}/100 ({thesis.get('health_grade', '?')})")

    if thesis.get("upcoming_catalysts"):
        bull_signals.append(
            f"{len(thesis['upcoming_catalysts'])} upcoming catalyst(s)"
        )

    # Risk
    risk = signals.get("risk", {})
    if risk.get("active_alerts"):
        for alert in risk["active_alerts"]:
            bear_signals.append(f"Risk alert: {alert.get('message', alert.get('type', 'unknown'))}")

    beta = risk.get("beta")
    if beta is not None and beta > 1.5:
        bear_signals.append(f"High beta: {beta:.2f}")

    max_dd = risk.get("max_drawdown")
    if max_dd is not None and max_dd < -0.15:
        bear_signals.append(f"Recent drawdown: {max_dd:.1%}")

    # Earnings
    earnings = signals.get("earnings", {})
    if earnings.get("revenue_surprise_pct") and earnings["revenue_surprise_pct"] > 0.02:
        bull_signals.append(f"Revenue beat: +{earnings['revenue_surprise_pct']:.1%}")
    elif earnings.get("revenue_surprise_pct") and earnings["revenue_surprise_pct"] < -0.02:
        bear_signals.append(f"Revenue miss: {earnings['revenue_surprise_pct']:.1%}")

    # Model
    model = signals.get("model", {})
    if model.get("upside_pct"):
        if model["upside_pct"] > 0.10:
            bull_signals.append(f"Model upside: +{model['upside_pct']:.1%}")
        elif model["upside_pct"] < -0.10:
            bear_signals.append(f"Model downside: {model['upside_pct']:.1%}")

    # P&L context
    pos_info = signals.get("position_info", {})
    unrealized_pnl_pct = pos_info.get("unrealized_pnl_pct")
    if unrealized_pnl_pct is not None:
        if unrealized_pnl_pct > 0.20:
            neutral_signals.append(f"Large unrealized gain: +{unrealized_pnl_pct:.1%} — consider taking partial profits")
        elif unrealized_pnl_pct < -0.15:
            bear_signals.append(f"Large unrealized loss: {unrealized_pnl_pct:.1%} — review thesis")

    total = len(bull_signals) + len(bear_signals) + len(neutral_signals) or 1
    return {
        "bull_signals": bull_signals,
        "bear_signals": bear_signals,
        "neutral_signals": neutral_signals,
        "bull_pct": round(len(bull_signals) / total, 2),
        "bear_pct": round(len(bear_signals) / total, 2),
        "signal_bias": (
            "bullish" if len(bull_signals) > len(bear_signals) + 2
            else "bearish" if len(bear_signals) > len(bull_signals) + 2
            else "mixed"
        ),
    }


def _build_debate_scaffold(ticker: str, signals: dict, summary: dict) -> dict:
    """Build the bull/bear debate scaffold for a single ticker.

    Adapted from TradingAgents' bull_researcher + bear_researcher + research_manager.
    """
    thesis = signals.get("thesis", {})

    return {
        "ticker": ticker,
        "signal_summary": summary,
        "investment_debate": {
            "bull_case": {
                "key_arguments": summary["bull_signals"],
                "thesis_alignment": thesis.get("core_thesis", "No thesis on file"),
                "position_type": thesis.get("position", "unknown"),
                "agent_analysis": None,  # To be filled by agent
            },
            "bear_case": {
                "key_arguments": summary["bear_signals"],
                "risk_factors": [
                    a.get("message", a.get("type", ""))
                    for a in signals.get("risk", {}).get("active_alerts", [])
                ],
                "agent_analysis": None,  # To be filled by agent
            },
            "research_verdict": None,  # Agent fills: bull/bear/neutral + reasoning
        },
        "risk_assessment": {
            "aggressive_view": {
                "perspective": "Maximize returns — lean into winners, add on dips",
                "agent_analysis": None,  # To be filled by agent
            },
            "conservative_view": {
                "perspective": "Preserve capital — trim overweight, hedge tail risk",
                "agent_analysis": None,  # To be filled by agent
            },
            "neutral_view": {
                "perspective": "Balance risk/reward — maintain position sizes, set stops",
                "agent_analysis": None,  # To be filled by agent
            },
            "risk_verdict": None,  # Agent fills final assessment
        },
    }


def generate(decision_date: date, ticker_filter: str | None = None) -> bool:
    """Generate debate scaffolds from collected signals."""
    date_str = decision_date.isoformat()
    io = ArtifactIO("_portfolio", "decisions")

    signals_data = io.read_json(f"{date_str}_signals.json")
    if not signals_data:
        print(f"  ✗  No signals for {date_str}. Run collect_signals.py first.")
        return False

    ticker_signals = signals_data.get("ticker_signals", {})
    if not ticker_signals:
        print("  ✗  No ticker signals found in data.")
        return False

    print(f"Generating debate scaffolds for {date_str}...")

    debates = {}
    for ticker, signals in ticker_signals.items():
        if ticker_filter and ticker != ticker_filter.upper():
            continue

        summary = _build_signal_summary(ticker, signals)
        debate = _build_debate_scaffold(ticker, signals, summary)
        debates[ticker] = debate

        bias = summary["signal_bias"]
        n_bull = len(summary["bull_signals"])
        n_bear = len(summary["bear_signals"])
        print(f"  {ticker}: {bias} bias ({n_bull} bull / {n_bear} bear signals)")

    output = {
        "decision_date": date_str,
        "portfolio_context": signals_data.get("portfolio", {}),
        "portfolio_risk": signals_data.get("portfolio_risk"),
        "debates": debates,
    }

    path = io.write_json(f"{date_str}_debates.json", output)
    print(f"\n  ✓  Debates written to {path}")
    return True


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate bull/bear debate scaffolds")
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Decision date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Filter to a single ticker",
    )
    args = parser.parse_args()
    decision_date = date.fromisoformat(args.date)
    ok = generate(decision_date, ticker_filter=args.ticker)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
