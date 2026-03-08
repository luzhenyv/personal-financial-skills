"""Valuation module — DCF, comparable companies, and scenario analysis.

Provides personal-investor-grade valuation using data from PostgreSQL.
No external paid APIs required — uses SEC EDGAR data + free sources.

Adapted from equity-research/skills/initiating-coverage (Task 3)
in financial-services-plugins, simplified for individual investors.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.db.models import (
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
)
from src.db.session import get_session

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────


@dataclass
class DCFResult:
    """Result of a DCF valuation."""

    ticker: str
    # Inputs
    projection_years: int
    revenue_growth_rates: list[float]
    operating_margin: float
    tax_rate: float
    capex_pct_revenue: float
    nwc_pct_revenue: float
    wacc: float
    terminal_growth: float
    # Outputs
    projected_fcf: list[float]
    terminal_value: float
    enterprise_value: float
    net_debt: float
    equity_value: float
    shares_outstanding: int
    implied_price: float
    # Sensitivity grid: list of (wacc, terminal_g, price)
    sensitivity: list[dict[str, float]] = field(default_factory=list)


@dataclass
class CompsResult:
    """Result of a comparable companies analysis."""

    ticker: str
    peers: list[dict[str, Any]]
    target_metrics: dict[str, Any]
    # Implied valuations from peer medians
    implied_pe: float | None
    implied_ps: float | None
    implied_ev_ebitda: float | None
    median_implied_price: float | None


@dataclass
class ScenarioResult:
    """Bull/Base/Bear scenario analysis."""

    ticker: str
    current_price: float | None
    scenarios: dict[str, dict[str, Any]]  # {bull/base/bear: {price, upside, ...}}


@dataclass
class ValuationSummary:
    """Combined valuation output."""

    ticker: str
    company_name: str
    current_price: float | None
    dcf: DCFResult | None
    comps: CompsResult | None
    scenarios: ScenarioResult | None
    recommendation: str  # BUY / HOLD / SELL
    target_price: float | None
    upside_pct: float | None


# ──────────────────────────────────────────────
# DCF Model
# ──────────────────────────────────────────────


def simple_dcf(
    ticker: str,
    revenue_growth: float = 0.10,
    revenue_growth_decay: float = 0.01,
    operating_margin: float | None = None,
    tax_rate: float = 0.21,
    capex_pct: float | None = None,
    nwc_pct: float = 0.05,
    wacc: float = 0.10,
    terminal_growth: float = 0.03,
    projection_years: int = 5,
    session: Session | None = None,
) -> DCFResult:
    """Run a simplified DCF valuation.

    Uses historical data from PostgreSQL to anchor assumptions.
    Personal investors can override any parameter.

    Args:
        ticker: Stock ticker
        revenue_growth: Base case annual revenue growth rate
        revenue_growth_decay: Annual decrease in growth rate (growth decelerates)
        operating_margin: Override operating margin (None = use historical avg)
        tax_rate: Corporate tax rate
        capex_pct: CapEx as % of revenue (None = use historical)
        nwc_pct: Net working capital change as % of revenue
        wacc: Weighted average cost of capital
        terminal_growth: Perpetuity growth rate
        projection_years: Number of years to project
        session: Optional DB session
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        # Load latest financials
        latest_inc = (
            session.query(IncomeStatement)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(desc(IncomeStatement.fiscal_year))
            .first()
        )
        latest_bs = (
            session.query(BalanceSheet)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(desc(BalanceSheet.fiscal_year))
            .first()
        )
        latest_cf = (
            session.query(CashFlowStatement)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(desc(CashFlowStatement.fiscal_year))
            .first()
        )
        metrics_list = (
            session.query(FinancialMetric)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(desc(FinancialMetric.fiscal_year))
            .limit(3)
            .all()
        )

        if not latest_inc or not latest_inc.revenue:
            raise ValueError(f"No income statement data for {ticker}")

        base_revenue = float(latest_inc.revenue)

        # Default operating margin from historical average
        if operating_margin is None:
            margins = [float(m.operating_margin) for m in metrics_list if m.operating_margin]
            operating_margin = sum(margins) / len(margins) if margins else 0.20

        # Default capex % from historical
        if capex_pct is None:
            if latest_cf and latest_cf.capital_expenditure and latest_inc.revenue:
                capex_pct = abs(float(latest_cf.capital_expenditure)) / float(latest_inc.revenue)
            else:
                capex_pct = 0.05

        # Shares outstanding
        shares = latest_inc.shares_diluted or latest_inc.shares_basic or 1
        shares = int(shares)

        # Net debt (for bridge from EV to equity value)
        cash = float(latest_bs.cash_and_equivalents or 0) if latest_bs else 0
        short_debt = float(latest_bs.short_term_debt or 0) if latest_bs else 0
        long_debt = float(latest_bs.long_term_debt or 0) if latest_bs else 0
        net_debt = short_debt + long_debt - cash

        # ── Project Free Cash Flows ──
        growth_rates = []
        projected_fcf = []
        revenue = base_revenue

        for yr in range(1, projection_years + 1):
            g = max(revenue_growth - revenue_growth_decay * (yr - 1), terminal_growth)
            growth_rates.append(g)
            revenue = revenue * (1 + g)
            ebit = revenue * operating_margin
            nopat = ebit * (1 - tax_rate)
            capex = revenue * capex_pct
            nwc_change = revenue * nwc_pct * 0.1  # Incremental NWC
            fcf = nopat - capex + (latest_cf.depreciation_amortization or 0) * 0.5 - nwc_change
            # Simplified: FCF ≈ NOPAT - CapEx + D&A adjustment - NWC change
            # For simplicity, use: FCF = NOPAT * (1 - reinvestment_rate)
            fcf_simple = nopat - capex - nwc_change
            projected_fcf.append(fcf_simple)

        # ── Terminal Value (Gordon Growth) ──
        terminal_fcf = projected_fcf[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)

        # ── Discount to Present Value ──
        pv_fcf = sum(
            fcf / (1 + wacc) ** yr
            for yr, fcf in enumerate(projected_fcf, 1)
        )
        pv_terminal = terminal_value / (1 + wacc) ** projection_years

        enterprise_value = pv_fcf + pv_terminal
        equity_value = enterprise_value - net_debt
        implied_price = equity_value / shares if shares > 0 else 0

        # ── Sensitivity Analysis ──
        sensitivity = []
        wacc_range = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
        tg_range = [terminal_growth - 0.01, terminal_growth, terminal_growth + 0.01]

        for w in wacc_range:
            for tg in tg_range:
                if w <= tg:
                    continue  # Invalid: WACC must exceed terminal growth
                tv = projected_fcf[-1] * (1 + tg) / (w - tg)
                pv_t = tv / (1 + w) ** projection_years
                pv_f = sum(f / (1 + w) ** y for y, f in enumerate(projected_fcf, 1))
                ev = pv_f + pv_t
                eq = ev - net_debt
                p = eq / shares if shares > 0 else 0
                sensitivity.append({"wacc": w, "terminal_growth": tg, "price": p})

        return DCFResult(
            ticker=ticker,
            projection_years=projection_years,
            revenue_growth_rates=growth_rates,
            operating_margin=operating_margin,
            tax_rate=tax_rate,
            capex_pct_revenue=capex_pct,
            nwc_pct_revenue=nwc_pct,
            wacc=wacc,
            terminal_growth=terminal_growth,
            projected_fcf=projected_fcf,
            terminal_value=terminal_value,
            enterprise_value=enterprise_value,
            net_debt=net_debt,
            equity_value=equity_value,
            shares_outstanding=shares,
            implied_price=implied_price,
            sensitivity=sensitivity,
        )

    finally:
        if own_session:
            session.close()


# ──────────────────────────────────────────────
# Comparable Companies
# ──────────────────────────────────────────────


def peer_comps(
    ticker: str,
    n_peers: int = 5,
    session: Session | None = None,
) -> CompsResult:
    """Find comparable companies and compute relative valuation.

    Uses SIC code to find peers in the database, then compares valuation multiples.
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        target_company = session.query(Company).filter_by(ticker=ticker).first()
        if not target_company:
            raise ValueError(f"Company {ticker} not found")

        # Get target's latest metrics
        target_metrics = (
            session.query(FinancialMetric)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(desc(FinancialMetric.fiscal_year))
            .first()
        )
        target_income = (
            session.query(IncomeStatement)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(desc(IncomeStatement.fiscal_year))
            .first()
        )
        target_price_row = (
            session.query(DailyPrice)
            .filter_by(ticker=ticker)
            .order_by(desc(DailyPrice.date))
            .first()
        )

        target_data = {
            "ticker": ticker,
            "name": target_company.name,
            "revenue": float(target_income.revenue) if target_income and target_income.revenue else None,
            "net_income": float(target_income.net_income) if target_income and target_income.net_income else None,
            "pe_ratio": float(target_metrics.pe_ratio) if target_metrics and target_metrics.pe_ratio else None,
            "ps_ratio": float(target_metrics.ps_ratio) if target_metrics and target_metrics.ps_ratio else None,
            "ev_to_ebitda": float(target_metrics.ev_to_ebitda) if target_metrics and target_metrics.ev_to_ebitda else None,
            "gross_margin": float(target_metrics.gross_margin) if target_metrics and target_metrics.gross_margin else None,
            "operating_margin": float(target_metrics.operating_margin) if target_metrics and target_metrics.operating_margin else None,
            "roe": float(target_metrics.roe) if target_metrics and target_metrics.roe else None,
            "revenue_growth": float(target_metrics.revenue_growth) if target_metrics and target_metrics.revenue_growth else None,
        }

        # Find peers by SIC code
        sic = target_company.sic_code
        peer_companies = (
            session.query(Company)
            .filter(Company.sic_code == sic, Company.ticker != ticker)
            .limit(n_peers)
            .all()
        ) if sic else []

        # If not enough SIC peers, get all other companies
        if len(peer_companies) < 2:
            peer_companies = (
                session.query(Company)
                .filter(Company.ticker != ticker)
                .limit(n_peers)
                .all()
            )

        peers = []
        for pc in peer_companies:
            pm = (
                session.query(FinancialMetric)
                .filter_by(ticker=pc.ticker, fiscal_quarter=None)
                .order_by(desc(FinancialMetric.fiscal_year))
                .first()
            )
            pi = (
                session.query(IncomeStatement)
                .filter_by(ticker=pc.ticker, fiscal_quarter=None)
                .order_by(desc(IncomeStatement.fiscal_year))
                .first()
            )
            if not pm:
                continue

            peers.append({
                "ticker": pc.ticker,
                "name": pc.name,
                "revenue": float(pi.revenue) if pi and pi.revenue else None,
                "pe_ratio": float(pm.pe_ratio) if pm.pe_ratio else None,
                "ps_ratio": float(pm.ps_ratio) if pm.ps_ratio else None,
                "ev_to_ebitda": float(pm.ev_to_ebitda) if pm.ev_to_ebitda else None,
                "gross_margin": float(pm.gross_margin) if pm.gross_margin else None,
                "operating_margin": float(pm.operating_margin) if pm.operating_margin else None,
                "roe": float(pm.roe) if pm.roe else None,
                "revenue_growth": float(pm.revenue_growth) if pm.revenue_growth else None,
            })

        # Compute median multiples
        def _median(values: list[float]) -> float | None:
            clean = sorted(v for v in values if v is not None and v > 0)
            if not clean:
                return None
            mid = len(clean) // 2
            return clean[mid] if len(clean) % 2 else (clean[mid - 1] + clean[mid]) / 2

        peer_pe = _median([p["pe_ratio"] for p in peers])
        peer_ps = _median([p["ps_ratio"] for p in peers])
        peer_ev = _median([p["ev_to_ebitda"] for p in peers])

        # Implied prices from peer medians
        shares = int(target_income.shares_diluted or target_income.shares_basic or 1) if target_income else 1
        eps = float(target_income.eps_diluted) if target_income and target_income.eps_diluted else None
        revenue_per_share = float(target_income.revenue) / shares if target_income and target_income.revenue and shares else None

        implied_pe_price = eps * peer_pe if eps and peer_pe else None
        implied_ps_price = revenue_per_share * peer_ps if revenue_per_share and peer_ps else None

        implied_prices = [p for p in [implied_pe_price, implied_ps_price] if p is not None]
        median_implied = _median(implied_prices) if implied_prices else None

        return CompsResult(
            ticker=ticker,
            peers=peers,
            target_metrics=target_data,
            implied_pe=implied_pe_price,
            implied_ps=implied_ps_price,
            implied_ev_ebitda=None,  # Needs EV calculation
            median_implied_price=median_implied,
        )

    finally:
        if own_session:
            session.close()


# ──────────────────────────────────────────────
# Scenario Analysis
# ──────────────────────────────────────────────


def scenario_analysis(
    ticker: str,
    bull_growth: float = 0.20,
    base_growth: float = 0.10,
    bear_growth: float = 0.02,
    wacc: float = 0.10,
    session: Session | None = None,
) -> ScenarioResult:
    """Run Bull/Base/Bear scenario analysis.

    Each scenario runs a DCF with different growth assumptions.
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        # Get current price
        price_row = (
            session.query(DailyPrice)
            .filter_by(ticker=ticker)
            .order_by(desc(DailyPrice.date))
            .first()
        )
        current_price = float(price_row.adjusted_close) if price_row else None

        scenarios = {}
        for name, growth, margin_adj, tg in [
            ("bull", bull_growth, 0.03, 0.035),       # Higher margin + growth
            ("base", base_growth, 0.0, 0.03),         # Current margins
            ("bear", bear_growth, -0.03, 0.02),       # Margin compression
        ]:
            # Get historical operating margin for adjustment
            metrics = (
                session.query(FinancialMetric)
                .filter_by(ticker=ticker, fiscal_quarter=None)
                .order_by(desc(FinancialMetric.fiscal_year))
                .limit(3)
                .all()
            )
            hist_margins = [float(m.operating_margin) for m in metrics if m.operating_margin]
            base_margin = sum(hist_margins) / len(hist_margins) if hist_margins else 0.20
            adj_margin = max(base_margin + margin_adj, 0.05)

            dcf = simple_dcf(
                ticker,
                revenue_growth=growth,
                operating_margin=adj_margin,
                wacc=wacc,
                terminal_growth=tg,
                session=session,
            )

            upside = None
            if current_price and current_price > 0:
                upside = (dcf.implied_price - current_price) / current_price

            scenarios[name] = {
                "revenue_growth": growth,
                "operating_margin": adj_margin,
                "terminal_growth": tg,
                "wacc": wacc,
                "implied_price": dcf.implied_price,
                "enterprise_value": dcf.enterprise_value,
                "equity_value": dcf.equity_value,
                "upside": upside,
            }

        return ScenarioResult(
            ticker=ticker,
            current_price=current_price,
            scenarios=scenarios,
        )

    finally:
        if own_session:
            session.close()


# ──────────────────────────────────────────────
# Combined Valuation Summary
# ──────────────────────────────────────────────


def valuation_summary(
    ticker: str,
    revenue_growth: float = 0.10,
    wacc: float = 0.10,
    session: Session | None = None,
) -> ValuationSummary:
    """Generate a complete valuation summary combining DCF, comps, and scenarios.

    This is the main entry point for the valuation module.
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        company = session.query(Company).filter_by(ticker=ticker).first()
        if not company:
            raise ValueError(f"Company {ticker} not found")

        price_row = (
            session.query(DailyPrice)
            .filter_by(ticker=ticker)
            .order_by(desc(DailyPrice.date))
            .first()
        )
        current_price = float(price_row.adjusted_close) if price_row else None

        # Run DCF
        dcf_result = None
        try:
            dcf_result = simple_dcf(ticker, revenue_growth=revenue_growth, wacc=wacc, session=session)
        except Exception as e:
            logger.warning(f"DCF failed for {ticker}: {e}")

        # Run comps
        comps_result = None
        try:
            comps_result = peer_comps(ticker, session=session)
        except Exception as e:
            logger.warning(f"Comps failed for {ticker}: {e}")

        # Run scenarios
        scenario_result = None
        try:
            scenario_result = scenario_analysis(ticker, base_growth=revenue_growth, wacc=wacc, session=session)
        except Exception as e:
            logger.warning(f"Scenarios failed for {ticker}: {e}")

        # Determine target price (weighted average of methods)
        prices = []
        if dcf_result and dcf_result.implied_price > 0:
            prices.append(("DCF", dcf_result.implied_price, 0.5))
        if comps_result and comps_result.median_implied_price:
            prices.append(("Comps", comps_result.median_implied_price, 0.3))
        if scenario_result and "base" in scenario_result.scenarios:
            base_price = scenario_result.scenarios["base"]["implied_price"]
            if base_price > 0:
                prices.append(("Scenario", base_price, 0.2))

        if prices:
            total_weight = sum(w for _, _, w in prices)
            target_price = sum(p * w for _, p, w in prices) / total_weight
        else:
            target_price = None

        # Recommendation
        if current_price and target_price:
            upside = (target_price - current_price) / current_price
            if upside > 0.15:
                recommendation = "BUY"
            elif upside < -0.10:
                recommendation = "SELL"
            else:
                recommendation = "HOLD"
        else:
            upside = None
            recommendation = "N/A"

        return ValuationSummary(
            ticker=ticker,
            company_name=company.name,
            current_price=current_price,
            dcf=dcf_result,
            comps=comps_result,
            scenarios=scenario_result,
            recommendation=recommendation,
            target_price=target_price,
            upside_pct=upside,
        )

    finally:
        if own_session:
            session.close()
