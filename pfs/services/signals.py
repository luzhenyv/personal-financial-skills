"""Signal aggregation service — collects multi-source signals per ticker.

Used by the fund-manager skill to gather quantitative inputs before
the bull/bear debate and trading decision phases.

Combines:
- Technical indicators (SMA, EMA, MACD, RSI, Bollinger, ATR, VWMA)
- Price momentum (returns over various windows)
- Risk metrics (beta, volatility, drawdown)
- Fundamental metrics (margins, growth, valuation)

Technical indicators adapted from TradingAgents' Market Analyst:
  SMA(50, 200), EMA(10), MACD/Signal/Histogram, RSI(14),
  Bollinger Bands(20,2), ATR(14), VWMA(20).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from pfs.db.models import Company, DailyPrice, Portfolio, Position
from pfs.services.risk import (
    _max_drawdown,
    _price_series,
    _returns_from_prices,
    ticker_risk,
)


# ── OHLCV fetcher ───────────────────────────────────────────


def _ohlcv_series(
    db: Session, ticker: str, start: date, end: date,
) -> dict[str, list[float]]:
    """Return OHLCV columns as separate lists, aligned by date."""
    rows = (
        db.query(
            DailyPrice.open_price,
            DailyPrice.high_price,
            DailyPrice.low_price,
            DailyPrice.close_price,
            DailyPrice.volume,
        )
        .filter(
            DailyPrice.ticker == ticker,
            DailyPrice.date >= start,
            DailyPrice.date <= end,
        )
        .order_by(DailyPrice.date)
        .all()
    )
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for o, h, l, c, v in rows:
        opens.append(float(o) if o is not None else 0.0)
        highs.append(float(h) if h is not None else 0.0)
        lows.append(float(l) if l is not None else 0.0)
        closes.append(float(c) if c is not None else 0.0)
        volumes.append(float(v) if v is not None else 0.0)
    return {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }


# ── Technical indicator computations ─────────────────────────


def _sma(data: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    arr = np.array(data)
    if len(arr) < period:
        return []
    kernel = np.ones(period) / period
    sma_full = np.convolve(arr, kernel, mode="valid")
    return sma_full.tolist()


def _ema(data: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if len(data) < period:
        return []
    arr = np.array(data, dtype=float)
    alpha = 2.0 / (period + 1)
    ema = np.empty_like(arr)
    ema[0] = arr[0]
    for i in range(1, len(arr)):
        ema[i] = alpha * arr[i] + (1 - alpha) * ema[i - 1]
    return ema.tolist()


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Relative Strength Index — returns latest value."""
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Wilder's smoothed average
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 2)


def _macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, float | None]:
    """MACD, Signal line, and Histogram — returns latest values."""
    if len(closes) < slow + signal:
        return {"macd": None, "macd_signal": None, "macd_histogram": None}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    # Align to the shorter (slow) EMA
    offset = len(ema_fast) - len(ema_slow)
    macd_line = [ema_fast[offset + i] - ema_slow[i] for i in range(len(ema_slow))]
    signal_line = _ema(macd_line, signal)
    if not signal_line:
        return {"macd": round(macd_line[-1], 4) if macd_line else None, "macd_signal": None, "macd_histogram": None}
    offset2 = len(macd_line) - len(signal_line)
    hist = macd_line[-1] - signal_line[-1]
    return {
        "macd": round(macd_line[-1], 4),
        "macd_signal": round(signal_line[-1], 4),
        "macd_histogram": round(hist, 4),
    }


def _bollinger_bands(
    closes: list[float], period: int = 20, num_std: float = 2.0,
) -> dict[str, float | None]:
    """Bollinger Bands — returns latest upper, middle, lower."""
    if len(closes) < period:
        return {"bb_upper": None, "bb_middle": None, "bb_lower": None, "bb_width": None, "bb_pct_b": None}
    window = closes[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window, ddof=1))
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = (upper - lower) / middle if middle != 0 else 0
    pct_b = (closes[-1] - lower) / (upper - lower) if (upper - lower) != 0 else 0.5
    return {
        "bb_upper": round(upper, 2),
        "bb_middle": round(middle, 2),
        "bb_lower": round(lower, 2),
        "bb_width": round(width, 4),
        "bb_pct_b": round(pct_b, 4),
    }


def _atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """Average True Range — returns latest value."""
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    # Wilder's smoothing
    atr_val = float(np.mean(trs[:period]))
    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
    return round(atr_val, 4)


def _vwma(
    closes: list[float], volumes: list[float], period: int = 20,
) -> float | None:
    """Volume Weighted Moving Average — returns latest value."""
    if len(closes) < period:
        return None
    c = np.array(closes[-period:])
    v = np.array(volumes[-period:])
    total_vol = v.sum()
    if total_vol == 0:
        return None
    return round(float(np.sum(c * v) / total_vol), 2)


# ── Composite signal builders ────────────────────────────────


def _technical_indicators(ohlcv: dict[str, list[float]]) -> dict[str, Any]:
    """Compute all technical indicators from OHLCV data.

    Matches TradingAgents' Market Analyst indicator set:
    SMA(50,200), EMA(10), MACD/Signal/Hist, RSI(14),
    Bollinger(20,2), ATR(14), VWMA(20).
    """
    closes = ohlcv["close"]
    highs = ohlcv["high"]
    lows = ohlcv["low"]
    volumes = ohlcv["volume"]

    if len(closes) < 20:
        return {"status": "insufficient_data", "min_bars_needed": 20}

    latest = closes[-1]

    # Moving Averages
    sma_50 = _sma(closes, 50)
    sma_200 = _sma(closes, 200)
    ema_10 = _ema(closes, 10)

    sma_50_val = round(sma_50[-1], 2) if sma_50 else None
    sma_200_val = round(sma_200[-1], 2) if sma_200 else None
    ema_10_val = round(ema_10[-1], 2) if ema_10 else None

    # MACD
    macd_vals = _macd(closes)

    # RSI
    rsi_val = _rsi(closes)

    # Bollinger Bands
    bb = _bollinger_bands(closes)

    # ATR
    atr_val = _atr(highs, lows, closes)

    # VWMA
    vwma_val = _vwma(closes, volumes)

    # Derived signals
    signals = {}

    # SMA crossover signals
    if sma_50_val and sma_200_val:
        signals["golden_cross"] = sma_50_val > sma_200_val
        signals["death_cross"] = sma_50_val < sma_200_val

    # RSI zones
    if rsi_val is not None:
        signals["rsi_overbought"] = rsi_val > 70
        signals["rsi_oversold"] = rsi_val < 30
        signals["rsi_zone"] = (
            "overbought" if rsi_val > 70
            else "oversold" if rsi_val < 30
            else "neutral"
        )

    # MACD crossover
    if macd_vals["macd"] is not None and macd_vals["macd_signal"] is not None:
        signals["macd_bullish"] = macd_vals["macd"] > macd_vals["macd_signal"]
        signals["macd_bearish"] = macd_vals["macd"] < macd_vals["macd_signal"]

    # Bollinger position
    if bb["bb_pct_b"] is not None:
        signals["bb_position"] = (
            "above_upper" if bb["bb_pct_b"] > 1.0
            else "below_lower" if bb["bb_pct_b"] < 0.0
            else "in_bands"
        )

    # Price vs moving averages
    if sma_50_val:
        signals["above_sma50"] = latest > sma_50_val
    if sma_200_val:
        signals["above_sma200"] = latest > sma_200_val
    if ema_10_val:
        signals["above_ema10"] = latest > ema_10_val
    if vwma_val:
        signals["above_vwma"] = latest > vwma_val

    return {
        "status": "ok",
        "moving_averages": {
            "sma_50": sma_50_val,
            "sma_200": sma_200_val,
            "ema_10": ema_10_val,
            "price_vs_sma50_pct": round((latest - sma_50_val) / sma_50_val, 4) if sma_50_val else None,
            "price_vs_sma200_pct": round((latest - sma_200_val) / sma_200_val, 4) if sma_200_val else None,
            "price_vs_ema10_pct": round((latest - ema_10_val) / ema_10_val, 4) if ema_10_val else None,
        },
        "macd": macd_vals,
        "rsi": rsi_val,
        "bollinger_bands": bb,
        "atr": atr_val,
        "vwma": vwma_val,
        "signals": signals,
    }


def _momentum_signals(
    prices: list[float],
) -> dict[str, float | None]:
    """Compute price momentum over 5d, 20d, 60d windows."""
    signals: dict[str, float | None] = {}
    for label, window in [("5d", 5), ("20d", 20), ("60d", 60)]:
        if len(prices) > window:
            ret = (prices[-1] - prices[-(window + 1)]) / prices[-(window + 1)]
            signals[f"return_{label}"] = round(ret, 4)
        else:
            signals[f"return_{label}"] = None
    return signals


def _volatility_signals(prices: list[float]) -> dict[str, float | None]:
    """Compute volatility-related signals."""
    rets = _returns_from_prices(prices)
    if len(rets) < 20:
        return {"annualized_vol": None, "max_drawdown_30d": None}
    vol = float(np.std(rets[-60:]) * math.sqrt(252)) if len(rets) >= 60 else float(np.std(rets) * math.sqrt(252))
    dd_30 = _max_drawdown(prices[-30:]) if len(prices) >= 30 else None
    return {
        "annualized_vol": round(vol, 4),
        "max_drawdown_30d": round(dd_30, 4) if dd_30 is not None else None,
    }


def aggregate_ticker_signals(
    db: Session,
    ticker: str,
    lookback_days: int = 30,
) -> dict[str, Any]:
    """Build a signal bundle for a single ticker."""
    end = date.today()
    # Need 200+ bars for SMA200, plus buffer for weekends
    start = end - timedelta(days=max(lookback_days + 60, 400))

    # Fetch full OHLCV for technical indicators
    ohlcv = _ohlcv_series(db, ticker, start, end)
    prices = ohlcv["close"]
    latest_price = prices[-1] if prices else None

    # Technical indicators (TradingAgents-style)
    technicals = _technical_indicators(ohlcv)

    # Momentum
    momentum = _momentum_signals(prices)

    # Volatility
    volatility = _volatility_signals(prices)

    # Risk
    risk = ticker_risk(db, ticker, lookback_days=max(lookback_days, 252))

    # Fundamental metrics from most recent data
    from pfs.services.financials import get_metrics
    metrics = {}
    try:
        raw_list = get_metrics(db, ticker)
        if raw_list:
            raw = raw_list[0] if isinstance(raw_list, list) else raw_list
            metrics = {
                "pe_ratio": raw.get("pe_ratio"),
                "revenue_growth": raw.get("revenue_growth"),
                "gross_margin": raw.get("gross_margin"),
                "net_margin": raw.get("net_margin"),
                "roe": raw.get("roe"),
                "roic": raw.get("roic"),
                "fcf_yield": raw.get("fcf_yield"),
                "debt_to_equity": raw.get("debt_to_equity"),
            }
    except Exception:
        pass

    return {
        "ticker": ticker,
        "as_of": end.isoformat(),
        "latest_price": latest_price,
        "technicals": technicals,
        "momentum": momentum,
        "volatility": volatility,
        "risk": {
            "beta": risk.get("beta"),
            "sharpe_ratio": risk.get("sharpe_ratio"),
            "max_drawdown": risk.get("max_drawdown"),
            "correlation": risk.get("correlation"),
        },
        "fundamentals": metrics,
    }


def aggregate_portfolio_signals(
    db: Session,
    portfolio_id: int,
    lookback_days: int = 30,
) -> dict[str, Any]:
    """Aggregate signals for every position in the portfolio."""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    positions = (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id, Position.shares > 0)
        .all()
    )

    tickers = [p.ticker for p in positions]
    signals = {}
    for t in tickers:
        signals[t] = aggregate_ticker_signals(db, t, lookback_days=lookback_days)

    return {
        "portfolio_id": portfolio_id,
        "as_of": date.today().isoformat(),
        "position_count": len(tickers),
        "tickers": tickers,
        "signals": signals,
    }
