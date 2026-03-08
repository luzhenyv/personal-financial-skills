"""Standalone DCF valuation engine.

This is the single canonical valuation model used across the project:
  - Streamlit app  → ``valuation_tab.py`` calls ``valuation_summary()``
  - CLI / scripts  → import and call directly
  - company-profile skill → can call ``valuation_summary()`` programmatically

Design goals
------------
* **Self-contained**: only needs PostgreSQL (via SQLAlchemy) + yfinance.
* **No Excel, no MCP servers, no hardcoded numbers**: all inputs derived from
  historical DB data and live market data.
* **One engine, three scenarios**: Bear / Base / Bull with graduated assumptions.
* **5×5 sensitivity table**: WACC × terminal-growth, full DCF recalculation per cell.

DCF methodology
---------------
  Revenue projection   : historical CAGR → linear deceleration to long-run rate
  Operating income     : revenue × operating_margin (stable or trend-adjusted)
  Unlevered FCF        : NOPAT + D&A − CapEx − ΔNWC
  Terminal value       : Gordon Growth  TV = FCF_5 × (1+g) / (WACC − g)
  Discounting          : end-of-year convention  PV = CF / (1+WACC)^t
  WACC                 : CAPM cost-of-equity + after-tax cost-of-debt
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

RISK_FREE_RATE: float = 0.0425   # ~10-year US Treasury (update as needed)
EQUITY_RISK_PREMIUM: float = 0.055
DEFAULT_BETA: float = 1.2
DEFAULT_COST_OF_DEBT: float = 0.05
DEFAULT_TAX_RATE: float = 0.21
TERMINAL_GROWTH_BASE: float = 0.025
LONG_RUN_GROWTH: float = 0.05    # revenue growth fade target (year 5)
PROJECTION_YEARS: int = 5

# Scenario multipliers applied to base-case assumptions
_SCENARIOS = {
    "bear": {"growth_mult": 0.60, "margin_delta": -0.03, "terminal_growth": 0.020},
    "base": {"growth_mult": 1.00, "margin_delta": 0.00,  "terminal_growth": TERMINAL_GROWTH_BASE},
    "bull": {"growth_mult": 1.40, "margin_delta": +0.02, "terminal_growth": 0.030},
}


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses (returned to callers / UI)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DCFResult:
    """Outputs of a single DCF run (one scenario / one assumption set)."""
    enterprise_value: float
    net_debt: float
    equity_value: float
    implied_price: float

    # Projection inputs used
    projection_years: int
    projected_fcf: list[float]
    revenue_growth_rates: list[float]
    operating_margin: float
    wacc: float
    terminal_growth: float
    tax_rate: float
    capex_pct_revenue: float
    shares_outstanding: float

    # 5×5 sensitivity: list of {"wacc", "terminal_growth", "price"}
    sensitivity: list[dict[str, float]] = field(default_factory=list)


@dataclass
class ScenariosResult:
    """Bear / Base / Bull implied prices."""
    scenarios: dict[str, dict[str, Any]]  # key = "bear"|"base"|"bull"


@dataclass
class CompsResult:
    """Peer comparison and implied prices from comps multiples."""
    peers: list[dict[str, Any]]
    target_metrics: dict[str, Any]
    implied_pe: float | None
    implied_ps: float | None
    median_implied_price: float | None


@dataclass
class ValuationResult:
    """Top-level result returned by ``valuation_summary()``."""
    recommendation: str           # "BUY" | "HOLD" | "SELL"
    target_price: float | None
    upside_pct: float | None
    dcf: DCFResult | None
    scenarios: ScenariosResult | None
    comps: CompsResult | None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def valuation_summary(
    ticker: str,
    *,
    revenue_growth: float | None = None,
    wacc: float | None = None,
) -> ValuationResult:
    """Run a full valuation for *ticker*.

    Args:
        ticker:         Company ticker (e.g. ``"NVDA"``).
        revenue_growth: Override for Year-1 revenue growth (decimal, e.g. ``0.20``).
                        If ``None``, derived from 3-year CAGR in the DB.
        wacc:           Override for WACC (decimal, e.g. ``0.10``).
                        If ``None``, computed from CAPM + balance sheet.

    Returns:
        :class:`ValuationResult` with DCF, scenarios, and comps.
    """
    hist = _load_historical_data(ticker)
    if not hist:
        return ValuationResult(
            recommendation="HOLD",
            target_price=None,
            upside_pct=None,
            dcf=None,
            scenarios=None,
            comps=None,
        )

    assumptions = _derive_assumptions(hist, revenue_growth_override=revenue_growth)
    current_price = _get_current_price(ticker)

    # WACC
    computed_wacc, *_ = _calc_wacc(
        ticker,
        tax_rate=assumptions["tax_rate"],
        net_debt=assumptions["net_debt"],
        wacc_override=wacc,
    )
    assumptions["wacc"] = computed_wacc

    # Base-case DCF
    dcf = _run_dcf(assumptions, terminal_growth=TERMINAL_GROWTH_BASE)

    # Sensitivity (5×5 grid) – full recompute per cell
    dcf.sensitivity = _build_sensitivity(assumptions)

    # Scenarios
    scenarios = _build_scenarios(assumptions, current_price)

    # Comps
    comps = _build_comps(ticker, hist, current_price)

    # Target price = weighted average: 50% DCF base, 40% comps median, 10% scenario avg
    target_price = _blended_target(dcf, scenarios, comps)

    # Recommendation
    recommendation = _rate(target_price, current_price)
    upside_pct = (
        (target_price / current_price - 1) if (target_price and current_price) else None
    )

    return ValuationResult(
        recommendation=recommendation,
        target_price=target_price,
        upside_pct=upside_pct,
        dcf=dcf,
        scenarios=scenarios,
        comps=comps,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_historical_data(ticker: str, years: int = 5) -> dict[str, Any] | None:
    """Fetch annual financials from PostgreSQL (last *years* years)."""
    try:
        from src.db.session import get_session
        from src.db.models import (
            IncomeStatement,
            BalanceSheet,
            CashFlowStatement,
            FinancialMetric,
        )

        session = get_session()
        try:
            incomes = (
                session.query(IncomeStatement)
                .filter(
                    IncomeStatement.ticker == ticker,
                    IncomeStatement.fiscal_quarter.is_(None),
                )
                .order_by(IncomeStatement.fiscal_year.desc())
                .limit(years)
                .all()
            )
            if not incomes:
                return None

            balances = (
                session.query(BalanceSheet)
                .filter(
                    BalanceSheet.ticker == ticker,
                    BalanceSheet.fiscal_quarter.is_(None),
                )
                .order_by(BalanceSheet.fiscal_year.desc())
                .limit(years)
                .all()
            )

            cash_flows = (
                session.query(CashFlowStatement)
                .filter(
                    CashFlowStatement.ticker == ticker,
                    CashFlowStatement.fiscal_quarter.is_(None),
                )
                .order_by(CashFlowStatement.fiscal_year.desc())
                .limit(years)
                .all()
            )

            metrics = (
                session.query(FinancialMetric)
                .filter(
                    FinancialMetric.ticker == ticker,
                    FinancialMetric.fiscal_quarter.is_(None),
                )
                .order_by(FinancialMetric.fiscal_year.desc())
                .limit(years)
                .all()
            )

            return {
                "incomes": list(reversed(incomes)),
                "balances": list(reversed(balances)),
                "cash_flows": list(reversed(cash_flows)),
                "metrics": list(reversed(metrics)),
            }
        finally:
            session.close()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Assumption derivation
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _derive_assumptions(
    hist: dict[str, Any],
    revenue_growth_override: float | None = None,
) -> dict[str, Any]:
    """Compute base-case DCF assumptions from historical data."""
    incomes = hist["incomes"]
    balances = hist["balances"]
    cash_flows = hist["cash_flows"]

    # ── Revenue CAGR (last 3 years, or all available) ──────────────────────
    revenues = [_safe_float(i.revenue) for i in incomes if i.revenue]
    if len(revenues) >= 2:
        # Use up to last 3Y for CAGR
        n = min(3, len(revenues) - 1)
        cagr = (revenues[-1] / revenues[-1 - n]) ** (1 / n) - 1
    else:
        cagr = 0.10  # fallback

    base_rev_growth = revenue_growth_override if revenue_growth_override is not None else cagr
    base_rev_growth = max(min(base_rev_growth, 2.0), -0.30)  # sanity clamp

    # ── Operating margin (3-year average) ──────────────────────────────────
    op_margins = [
        _safe_float(i.operating_income) / _safe_float(i.revenue)
        for i in incomes
        if i.operating_income and i.revenue and _safe_float(i.revenue) > 0
    ]
    operating_margin = sum(op_margins[-3:]) / len(op_margins[-3:]) if op_margins else 0.15

    # ── Tax rate (3-year average) ───────────────────────────────────────────
    tax_rates = [
        _safe_float(i.income_tax) / _safe_float(i.pretax_income)
        for i in incomes
        if i.income_tax and i.pretax_income and _safe_float(i.pretax_income) > 0
    ]
    tax_rate = sum(tax_rates[-3:]) / len(tax_rates[-3:]) if tax_rates else DEFAULT_TAX_RATE
    tax_rate = max(0.05, min(0.40, tax_rate))  # clamp 5–40%

    # ── D&A as % of revenue ─────────────────────────────────────────────────
    da_pcts = [
        _safe_float(cf.depreciation_amortization) / _safe_float(i.revenue)
        for cf, i in zip(cash_flows, incomes)
        if cf.depreciation_amortization and i.revenue and _safe_float(i.revenue) > 0
    ]
    da_pct = sum(da_pcts[-3:]) / len(da_pcts[-3:]) if da_pcts else 0.03

    # ── CapEx as % of revenue ───────────────────────────────────────────────
    capex_pcts = [
        abs(_safe_float(cf.capital_expenditure)) / _safe_float(i.revenue)
        for cf, i in zip(cash_flows, incomes)
        if cf.capital_expenditure and i.revenue and _safe_float(i.revenue) > 0
    ]
    capex_pct = sum(capex_pcts[-3:]) / len(capex_pcts[-3:]) if capex_pcts else 0.04

    # ── NWC change as % of revenue change ──────────────────────────────────
    nwc_pcts = []
    for idx in range(1, len(cash_flows)):
        nwc = _safe_float(cash_flows[idx].change_in_working_capital)
        rev_delta = _safe_float(incomes[idx].revenue) - _safe_float(incomes[idx - 1].revenue)
        if rev_delta != 0:
            nwc_pcts.append(nwc / rev_delta)
    nwc_pct = sum(nwc_pcts[-3:]) / len(nwc_pcts[-3:]) if nwc_pcts else 0.01

    # ── Balance sheet (most recent) ─────────────────────────────────────────
    latest_bs = balances[-1] if balances else None
    cash = _safe_float(latest_bs.cash_and_equivalents if latest_bs else None)
    short_debt = _safe_float(latest_bs.short_term_debt if latest_bs else None)
    long_debt = _safe_float(latest_bs.long_term_debt if latest_bs else None)
    total_debt = short_debt + long_debt
    net_debt = total_debt - cash  # negative = net cash position

    # ── Shares outstanding (diluted, most recent) ───────────────────────────
    latest_inc = incomes[-1] if incomes else None
    shares = _safe_float(latest_inc.shares_diluted if latest_inc else None)
    if shares < 1:  # probably stored as actual count, not millions
        shares = 1e6  # fallback

    # ── Latest revenue (base for projections) ───────────────────────────────
    latest_revenue = _safe_float(latest_inc.revenue if latest_inc else None)

    return {
        "base_rev_growth": base_rev_growth,
        "operating_margin": operating_margin,
        "tax_rate": tax_rate,
        "da_pct": da_pct,
        "capex_pct": capex_pct,
        "nwc_pct": nwc_pct,
        "net_debt": net_debt,
        "shares": shares,
        "latest_revenue": latest_revenue,
        "wacc": None,  # filled in by caller after _calc_wacc()
    }


# ─────────────────────────────────────────────────────────────────────────────
# WACC
# ─────────────────────────────────────────────────────────────────────────────

def _calc_wacc(
    ticker: str,
    tax_rate: float,
    net_debt: float,
    wacc_override: float | None = None,
) -> tuple[float, float, float, float]:
    """Return (wacc, beta, cost_of_equity, cost_of_debt)."""
    if wacc_override is not None:
        return wacc_override, DEFAULT_BETA, wacc_override, DEFAULT_COST_OF_DEBT

    beta = DEFAULT_BETA
    market_cap: float | None = None

    try:
        from src.etl.yfinance_client import get_stock_info

        info = get_stock_info(ticker)
        raw_beta = info.get("beta")
        if raw_beta and float(raw_beta) > 0:
            beta = float(raw_beta)
        mc = info.get("market_cap")
        if mc:
            market_cap = float(mc)
    except Exception:
        pass

    cost_of_equity = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM
    cost_of_debt = DEFAULT_COST_OF_DEBT

    # Equity / debt weights using market values
    if market_cap and market_cap > 0:
        debt_value = max(net_debt, 0.0)  # treat net-cash as 0 debt
        total_capital = market_cap + debt_value
        equity_w = market_cap / total_capital
        debt_w = debt_value / total_capital
    else:
        equity_w, debt_w = 0.85, 0.15

    after_tax_kd = cost_of_debt * (1.0 - tax_rate)
    wacc = equity_w * cost_of_equity + debt_w * after_tax_kd
    wacc = max(0.06, min(0.25, wacc))  # clamp 6–25%

    return wacc, beta, cost_of_equity, cost_of_debt


# ─────────────────────────────────────────────────────────────────────────────
# Core DCF calculation
# ─────────────────────────────────────────────────────────────────────────────

def _build_growth_schedule(
    base_growth: float,
    years: int = PROJECTION_YEARS,
    long_run: float = LONG_RUN_GROWTH,
) -> list[float]:
    """Linearly decelerate from *base_growth* to *long_run* over *years*."""
    floor = min(base_growth, long_run)
    return [
        base_growth + (long_run - base_growth) * i / max(years - 1, 1)
        for i in range(years)
    ]


def _calc_dcf_core(
    latest_revenue: float,
    growth_rates: list[float],
    operating_margin: float,
    tax_rate: float,
    da_pct: float,
    capex_pct: float,
    nwc_pct: float,
    wacc: float,
    terminal_growth: float,
    net_debt: float,
    shares: float,
) -> tuple[float, float, float, list[float]]:
    """Pure DCF calculation.  Returns (enterprise_value, equity_value, implied_price, projected_fcfs)."""
    years = len(growth_rates)
    projected_revenue = []
    rev = latest_revenue
    for g in growth_rates:
        rev = rev * (1.0 + g)
        projected_revenue.append(rev)

    prev_rev = latest_revenue
    fcfs: list[float] = []
    for rev in projected_revenue:
        ebit = rev * operating_margin
        nopat = ebit * (1.0 - tax_rate)
        da = rev * da_pct
        capex = rev * capex_pct
        delta_nwc = (rev - prev_rev) * nwc_pct
        fcf = nopat + da - capex - delta_nwc
        fcfs.append(fcf)
        prev_rev = rev

    # Terminal value (Gordon Growth, end-of-year convention)
    terminal_fcf = fcfs[-1] * (1.0 + terminal_growth)
    if wacc <= terminal_growth:
        # Prevents division by zero / negative TV
        tv = fcfs[-1] * 15.0  # fallback: 15× exit multiple
    else:
        tv = terminal_fcf / (wacc - terminal_growth)

    # Discount all cash flows
    pv_fcfs = sum(fcf / (1.0 + wacc) ** (t + 1) for t, fcf in enumerate(fcfs))
    pv_tv = tv / (1.0 + wacc) ** years

    enterprise_value = pv_fcfs + pv_tv
    equity_value = enterprise_value - net_debt  # net_debt negative = net cash
    implied_price = equity_value / shares if shares > 0 else 0.0

    return enterprise_value, equity_value, implied_price, fcfs


def _run_dcf(
    assumptions: dict[str, Any],
    terminal_growth: float = TERMINAL_GROWTH_BASE,
) -> DCFResult:
    """Run the base-case DCF and return a :class:`DCFResult`."""
    growth_rates = _build_growth_schedule(assumptions["base_rev_growth"])

    ev, equity_val, price, fcfs = _calc_dcf_core(
        latest_revenue=assumptions["latest_revenue"],
        growth_rates=growth_rates,
        operating_margin=assumptions["operating_margin"],
        tax_rate=assumptions["tax_rate"],
        da_pct=assumptions["da_pct"],
        capex_pct=assumptions["capex_pct"],
        nwc_pct=assumptions["nwc_pct"],
        wacc=assumptions["wacc"],
        terminal_growth=terminal_growth,
        net_debt=assumptions["net_debt"],
        shares=assumptions["shares"],
    )

    return DCFResult(
        enterprise_value=ev,
        net_debt=assumptions["net_debt"],
        equity_value=equity_val,
        implied_price=price,
        projection_years=PROJECTION_YEARS,
        projected_fcf=fcfs,
        revenue_growth_rates=growth_rates,
        operating_margin=assumptions["operating_margin"],
        wacc=assumptions["wacc"],
        terminal_growth=terminal_growth,
        tax_rate=assumptions["tax_rate"],
        capex_pct_revenue=assumptions["capex_pct"],
        shares_outstanding=assumptions["shares"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sensitivity Analysis (WACC × Terminal Growth, 5×5 = 25 cells)
# ─────────────────────────────────────────────────────────────────────────────

def _build_sensitivity(assumptions: dict[str, Any]) -> list[dict[str, float]]:
    """Build a 25-cell sensitivity table (full DCF per cell, no approximations)."""
    base_wacc = assumptions["wacc"]
    growth_rates = _build_growth_schedule(assumptions["base_rev_growth"])

    wacc_steps = [base_wacc + delta for delta in (-0.02, -0.01, 0.0, +0.01, +0.02)]
    tg_steps = [0.015, 0.020, 0.025, 0.030, 0.035]

    table: list[dict[str, float]] = []
    for w in wacc_steps:
        for tg in tg_steps:
            w_clamped = max(0.06, min(0.25, w))
            _, _, price, _ = _calc_dcf_core(
                latest_revenue=assumptions["latest_revenue"],
                growth_rates=growth_rates,
                operating_margin=assumptions["operating_margin"],
                tax_rate=assumptions["tax_rate"],
                da_pct=assumptions["da_pct"],
                capex_pct=assumptions["capex_pct"],
                nwc_pct=assumptions["nwc_pct"],
                wacc=w_clamped,
                terminal_growth=tg,
                net_debt=assumptions["net_debt"],
                shares=assumptions["shares"],
            )
            table.append({"wacc": w_clamped, "terminal_growth": tg, "price": price})

    return table


# ─────────────────────────────────────────────────────────────────────────────
# Scenario Analysis
# ─────────────────────────────────────────────────────────────────────────────

def _build_scenarios(
    assumptions: dict[str, Any],
    current_price: float | None,
) -> ScenariosResult:
    """Run Bear / Base / Bull DCFs and return implied prices."""
    results: dict[str, dict[str, Any]] = {}

    for name, params in _SCENARIOS.items():
        growth = max(assumptions["base_rev_growth"] * params["growth_mult"], -0.20)
        margin = assumptions["operating_margin"] + params["margin_delta"]
        tg = params["terminal_growth"]

        growth_rates = _build_growth_schedule(growth)
        _, _, price, _ = _calc_dcf_core(
            latest_revenue=assumptions["latest_revenue"],
            growth_rates=growth_rates,
            operating_margin=margin,
            tax_rate=assumptions["tax_rate"],
            da_pct=assumptions["da_pct"],
            capex_pct=assumptions["capex_pct"],
            nwc_pct=assumptions["nwc_pct"],
            wacc=assumptions["wacc"],
            terminal_growth=tg,
            net_debt=assumptions["net_debt"],
            shares=assumptions["shares"],
        )

        upside = (price / current_price - 1) if (current_price and current_price > 0) else None
        results[name] = {
            "revenue_growth": growth,
            "operating_margin": margin,
            "terminal_growth": tg,
            "implied_price": price,
            "upside": upside,
        }

    return ScenariosResult(scenarios=results)


# ─────────────────────────────────────────────────────────────────────────────
# Peer Comparables
# ─────────────────────────────────────────────────────────────────────────────

def _build_comps(
    ticker: str,
    hist: dict[str, Any],
    current_price: float | None,
) -> CompsResult | None:
    """Build comps from ``comps_table.json`` if available, else return None."""
    comps_path = Path("data/processed") / ticker / "comps_table.json"
    if not comps_path.exists():
        return None

    try:
        comps_data = json.loads(comps_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    peers_raw = comps_data.get("peers", [])
    if not peers_raw:
        return None

    # Normalise peer dicts to what the UI expects
    peers: list[dict[str, Any]] = []
    for p in peers_raw:
        peers.append({
            "ticker": p.get("ticker", ""),
            "name": p.get("name") or p.get("short_name", ""),
            "pe_ratio": _safe_float(p.get("pe_ratio") or p.get("pe_forward"), 0) or None,
            "ps_ratio": _safe_float(p.get("ps_ratio") or p.get("price_to_sales"), 0) or None,
            "ev_to_ebitda": _safe_float(p.get("ev_to_ebitda"), 0) or None,
            "gross_margin": _safe_float(p.get("gross_margin"), 0) or None,
            "operating_margin": _safe_float(p.get("operating_margin"), 0) or None,
        })

    # Target metrics from live yfinance
    target_metrics: dict[str, Any] = {"ticker": ticker}
    try:
        from src.etl.yfinance_client import get_stock_info

        info = get_stock_info(ticker)
        target_metrics.update({
            "name": info.get("name", ticker),
            "pe_ratio": info.get("pe_forward") or info.get("pe_ratio"),
            "ps_ratio": info.get("ps_ratio") or info.get("price_to_sales"),
            "ev_to_ebitda": info.get("ev_to_ebitda"),
            "gross_margin": info.get("gross_margins"),
            "operating_margin": info.get("operating_margins"),
        })
    except Exception:
        pass

    # EPS-derived implied prices from peer median multiples
    latest_inc = hist["incomes"][-1] if hist["incomes"] else None
    ltm_eps = _safe_float(latest_inc.eps_diluted if latest_inc else None)
    ltm_revenue = _safe_float(latest_inc.revenue if latest_inc else None)
    shares = _safe_float(latest_inc.shares_diluted if latest_inc else None)
    ltm_revenue_per_share = (ltm_revenue / shares) if shares > 0 else 0.0

    def _median(vals: list[float]) -> float | None:
        clean = sorted(v for v in vals if v and v > 0)
        if not clean:
            return None
        mid = len(clean) // 2
        return clean[mid] if len(clean) % 2 else (clean[mid - 1] + clean[mid]) / 2

    peer_pes = [p["pe_ratio"] for p in peers if p.get("pe_ratio")]
    peer_pss = [p["ps_ratio"] for p in peers if p.get("ps_ratio")]

    median_pe = _median([_safe_float(v) for v in peer_pes])
    median_ps = _median([_safe_float(v) for v in peer_pss])

    implied_pe = (median_pe * ltm_eps) if (median_pe and ltm_eps) else None
    implied_ps = (median_ps * ltm_revenue_per_share) if (median_ps and ltm_revenue_per_share) else None

    candidates = [p for p in [implied_pe, implied_ps] if p and p > 0]
    median_implied = sum(candidates) / len(candidates) if candidates else None

    return CompsResult(
        peers=peers,
        target_metrics=target_metrics,
        implied_pe=implied_pe,
        implied_ps=implied_ps,
        median_implied_price=median_implied,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Target price blend & rating
# ─────────────────────────────────────────────────────────────────────────────

def _blended_target(
    dcf: DCFResult | None,
    scenarios: ScenariosResult | None,
    comps: CompsResult | None,
) -> float | None:
    """Weighted average: 50% DCF base + 40% comps median + 10% scenario avg."""
    components: list[tuple[float, float]] = []  # (weight, price)

    if dcf and dcf.implied_price > 0:
        components.append((0.50, dcf.implied_price))

    comps_price = comps.median_implied_price if comps else None
    if comps_price and comps_price > 0:
        components.append((0.40, comps_price))

    if scenarios:
        base = scenarios.scenarios.get("base", {}).get("implied_price")
        if base and base > 0:
            components.append((0.10, base))

    if not components:
        return None

    total_w = sum(w for w, _ in components)
    return sum(w * p for w, p in components) / total_w


def _rate(target: float | None, current: float | None) -> str:
    """Buy / Hold / Sell based on upside vs target."""
    if not target or not current or current <= 0:
        return "HOLD"
    upside = target / current - 1
    if upside > 0.10:
        return "BUY"
    if upside < -0.10:
        return "SELL"
    return "HOLD"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_current_price(ticker: str) -> float | None:
    try:
        from src.etl.yfinance_client import get_current_price

        return get_current_price(ticker)
    except Exception:
        return None
