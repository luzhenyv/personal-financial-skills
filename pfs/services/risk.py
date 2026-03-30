"""Risk analytics service — portfolio-level and per-ticker risk metrics.

Computes beta, VaR, Sharpe, Sortino, max drawdown, and correlation
using daily price history from the database.  Called by the analysis
router to serve ``POST /api/analysis/risk/portfolio`` and
``GET /api/analysis/risk/{ticker}``.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from pfs.db.models import Company, DailyPrice, Position, Portfolio


# ── Helpers ──────────────────────────────────────────────────


def _price_series(
    db: Session, ticker: str, start: date, end: date
) -> list[float]:
    """Return a list of daily close prices for *ticker* between dates."""
    rows = (
        db.query(DailyPrice.close_price)
        .filter(
            DailyPrice.ticker == ticker,
            DailyPrice.date >= start,
            DailyPrice.date <= end,
        )
        .order_by(DailyPrice.date)
        .all()
    )
    return [float(r[0]) for r in rows if r[0] is not None]


def _returns_from_prices(prices: list[float]) -> np.ndarray:
    """Compute simple daily returns from a price series."""
    if len(prices) < 2:
        return np.array([])
    arr = np.array(prices)
    return (arr[1:] - arr[:-1]) / arr[:-1]


def _max_drawdown(prices: list[float]) -> float:
    """Compute maximum drawdown from a price series."""
    if len(prices) < 2:
        return 0.0
    peak = prices[0]
    max_dd = 0.0
    for p in prices[1:]:
        if p > peak:
            peak = p
        dd = (p - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


# ── Per-Ticker Risk ──────────────────────────────────────────


def ticker_risk(
    db: Session,
    ticker: str,
    benchmark: str = "SPY",
    lookback_days: int = 252,
) -> dict[str, Any]:
    """Compute per-ticker risk metrics relative to a benchmark.

    Returns beta, annualized volatility, correlation to benchmark,
    max drawdown, and Sharpe ratio.
    """
    end = date.today()
    start = end - timedelta(days=lookback_days + 60)  # buffer for weekends

    prices = _price_series(db, ticker.upper(), start, end)
    bench_prices = _price_series(db, benchmark.upper(), start, end)

    if len(prices) < 30 or len(bench_prices) < 30:
        return {
            "ticker": ticker.upper(),
            "benchmark": benchmark.upper(),
            "error": "Insufficient price history (need >= 30 trading days)",
            "beta": None,
            "annualized_volatility": None,
            "correlation": None,
            "max_drawdown": None,
            "sharpe_ratio": None,
        }

    # Align lengths (use the shorter series from the tail end)
    min_len = min(len(prices), len(bench_prices))
    prices = prices[-min_len:]
    bench_prices = bench_prices[-min_len:]

    ret = _returns_from_prices(prices)
    bench_ret = _returns_from_prices(bench_prices)
    min_ret_len = min(len(ret), len(bench_ret))
    ret = ret[-min_ret_len:]
    bench_ret = bench_ret[-min_ret_len:]

    # Beta = Cov(r, rb) / Var(rb)
    cov_matrix = np.cov(ret, bench_ret)
    beta = float(cov_matrix[0, 1] / cov_matrix[1, 1]) if cov_matrix[1, 1] != 0 else 0.0

    # Correlation
    corr = float(np.corrcoef(ret, bench_ret)[0, 1]) if len(ret) > 1 else 0.0

    # Annualized volatility
    ann_vol = float(np.std(ret) * math.sqrt(252))

    # Sharpe (assume risk-free = 4.5% / 252)
    rf_daily = 0.045 / 252
    excess = ret - rf_daily
    sharpe = float(np.mean(excess) / np.std(excess) * math.sqrt(252)) if np.std(excess) > 0 else 0.0

    return {
        "ticker": ticker.upper(),
        "benchmark": benchmark.upper(),
        "beta": round(beta, 3),
        "annualized_volatility": round(ann_vol, 4),
        "correlation": round(corr, 3),
        "max_drawdown": round(_max_drawdown(prices), 4),
        "sharpe_ratio": round(sharpe, 2),
        "trading_days": min_ret_len,
    }


# ── Portfolio Risk ────────────────────────────────────────────


def portfolio_risk(
    db: Session,
    portfolio_id: int = 1,
    benchmark: str = "SPY",
    lookback_days: int = 252,
) -> dict[str, Any]:
    """Compute portfolio-level risk metrics.

    Returns portfolio beta, VaR, Sharpe, Sortino, max drawdown,
    correlation matrix, and per-position risk contribution.
    """
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    positions = (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id)
        .all()
    )
    if not positions:
        return {
            "portfolio_id": portfolio_id,
            "benchmark": benchmark,
            "error": "No positions in portfolio",
            "portfolio_beta": None,
            "var_95_1d": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown_30d": None,
            "per_position": [],
            "correlation_matrix": {},
        }

    end = date.today()
    start = end - timedelta(days=lookback_days + 60)

    # Collect price series and compute weights
    tickers = [p.ticker for p in positions]

    # Get latest prices for weight computation
    from pfs.services.portfolio import _batch_latest_prices
    latest_prices = _batch_latest_prices(db, tickers)

    total_market = sum(
        Decimal(str(p.shares)) * latest_prices.get(p.ticker, Decimal(str(p.avg_cost)))
        for p in positions
    )
    if total_market == 0:
        raise ValueError("Portfolio has zero market value")

    weights: dict[str, float] = {}
    for p in positions:
        price = latest_prices.get(p.ticker, Decimal(str(p.avg_cost)))
        mv = Decimal(str(p.shares)) * price
        weights[p.ticker] = float(mv / total_market)

    # Collect return series
    returns_map: dict[str, np.ndarray] = {}
    prices_map: dict[str, list[float]] = {}
    for ticker in tickers:
        prices_list = _price_series(db, ticker, start, end)
        if len(prices_list) >= 30:
            prices_map[ticker] = prices_list
            returns_map[ticker] = _returns_from_prices(prices_list)

    bench_prices = _price_series(db, benchmark.upper(), start, end)
    bench_ret = _returns_from_prices(bench_prices) if len(bench_prices) >= 30 else np.array([])

    # Find common length across all return series
    all_lens = [len(r) for r in returns_map.values()]
    if bench_ret.size > 0:
        all_lens.append(len(bench_ret))
    if not all_lens:
        return {
            "portfolio_id": portfolio_id,
            "benchmark": benchmark,
            "error": "Insufficient price history across positions",
            "portfolio_beta": None,
            "var_95_1d": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown_30d": None,
            "per_position": [],
            "correlation_matrix": {},
        }

    common_len = min(all_lens)
    for ticker in list(returns_map.keys()):
        returns_map[ticker] = returns_map[ticker][-common_len:]
    if bench_ret.size > 0:
        bench_ret = bench_ret[-common_len:]

    # Portfolio return series (weighted sum)
    active_tickers = [t for t in tickers if t in returns_map]
    if not active_tickers:
        return {
            "portfolio_id": portfolio_id,
            "benchmark": benchmark,
            "error": "No tickers with sufficient price history",
            "portfolio_beta": None,
            "var_95_1d": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown_30d": None,
            "per_position": [],
            "correlation_matrix": {},
        }

    # Renormalize weights for active tickers only
    active_weight_sum = sum(weights[t] for t in active_tickers)
    active_weights = {t: weights[t] / active_weight_sum for t in active_tickers} if active_weight_sum > 0 else {t: 1.0 / len(active_tickers) for t in active_tickers}

    port_ret = np.zeros(common_len)
    for t in active_tickers:
        port_ret += active_weights[t] * returns_map[t]

    # Portfolio beta
    port_beta = None
    if bench_ret.size > 0 and len(bench_ret) == common_len:
        cov_m = np.cov(port_ret, bench_ret)
        port_beta = round(float(cov_m[0, 1] / cov_m[1, 1]), 3) if cov_m[1, 1] != 0 else 0.0

    # VaR (95%, 1-day, parametric)
    port_std = float(np.std(port_ret))
    port_mean = float(np.mean(port_ret))
    total_value = float(total_market)
    var_95 = round(total_value * (port_mean - 1.645 * port_std), 2)

    # Sharpe ratio (annualized, rf = 4.5%)
    rf_daily = 0.045 / 252
    excess = port_ret - rf_daily
    sharpe = round(float(np.mean(excess) / np.std(excess) * math.sqrt(252)), 2) if np.std(excess) > 0 else 0.0

    # Sortino ratio (downside deviation only)
    downside = excess[excess < 0]
    downside_std = float(np.std(downside)) if len(downside) > 0 else 0.0
    sortino = round(float(np.mean(excess) / downside_std * math.sqrt(252)), 2) if downside_std > 0 else 0.0

    # Max drawdown (last 30 trading days)
    port_prices_30d = (1 + port_ret[-min(30, common_len):]).cumprod()
    max_dd_30d = round(_max_drawdown(port_prices_30d.tolist()), 4)

    # Correlation matrix
    corr_matrix: dict[str, dict[str, float]] = {}
    if len(active_tickers) > 1:
        ret_arrays = np.array([returns_map[t] for t in active_tickers])
        corr = np.corrcoef(ret_arrays)
        for i, t1 in enumerate(active_tickers):
            corr_matrix[t1] = {}
            for j, t2 in enumerate(active_tickers):
                corr_matrix[t1][t2] = round(float(corr[i, j]), 3)

    # Per-position risk contribution
    per_position = []
    for t in active_tickers:
        t_ret = returns_map[t]
        t_vol = float(np.std(t_ret) * math.sqrt(252))
        t_beta = None
        t_corr_bench = None
        if bench_ret.size > 0 and len(bench_ret) == common_len:
            cm = np.cov(t_ret, bench_ret)
            t_beta = round(float(cm[0, 1] / cm[1, 1]), 3) if cm[1, 1] != 0 else 0.0
            t_corr_bench = round(float(np.corrcoef(t_ret, bench_ret)[0, 1]), 3)

        # Marginal VaR contribution (approximate)
        t_corr_port = float(np.corrcoef(t_ret, port_ret)[0, 1]) if len(t_ret) > 1 else 0.0
        marginal_var = round(
            active_weights[t] * t_vol * t_corr_port * total_value * 1.645 / math.sqrt(252),
            2,
        )

        per_position.append({
            "ticker": t,
            "weight": round(weights[t], 4),
            "beta": t_beta,
            "annualized_volatility": round(t_vol, 4),
            "correlation_to_benchmark": t_corr_bench,
            "correlation_to_portfolio": round(t_corr_port, 3),
            "marginal_var_95": marginal_var,
        })

    return {
        "portfolio_id": portfolio_id,
        "benchmark": benchmark,
        "portfolio_beta": port_beta,
        "var_95_1d": var_95,
        "sharpe_ratio_90d": sharpe,
        "sortino_ratio_90d": sortino,
        "max_drawdown_30d": max_dd_30d,
        "portfolio_volatility": round(float(np.std(port_ret) * math.sqrt(252)), 4),
        "total_market_value": total_value,
        "trading_days": common_len,
        "per_position": sorted(per_position, key=lambda x: -(x.get("marginal_var_95") or 0)),
        "correlation_matrix": corr_matrix,
    }
