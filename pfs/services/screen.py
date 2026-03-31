"""Stock screening service — parameterized filtering across all companies.

Called by ``GET /api/analysis/screen`` so that skill scripts (especially
idea-generation) can run server-side screens without pulling the full DB.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from pfs.db.models import Company, FinancialMetric, IncomeStatement


# ── Screening ────────────────────────────────────────────────


def screen_companies(
    db: Session,
    *,
    screen_type: str | None = None,
    # Growth filters
    min_revenue_growth: float | None = None,
    max_revenue_growth: float | None = None,
    min_eps_growth: float | None = None,
    # Value filters
    max_pe: float | None = None,
    min_pe: float | None = None,
    max_ps: float | None = None,
    max_ev_ebitda: float | None = None,
    min_fcf_yield: float | None = None,
    # Quality filters
    min_roe: float | None = None,
    min_roic: float | None = None,
    min_gross_margin: float | None = None,
    min_operating_margin: float | None = None,
    min_net_margin: float | None = None,
    # Balance sheet filters
    max_debt_to_equity: float | None = None,
    min_current_ratio: float | None = None,
    # Size filters
    min_revenue: int | None = None,
    min_market_cap: int | None = None,
    # Sector filter
    sector: str | None = None,
    # Sorting / limits
    sort_by: str = "revenue_growth",
    sort_desc: bool = True,
    limit: int = 25,
) -> dict[str, Any]:
    """Run a parameterized stock screen across all ingested companies.

    Applies preset filters for ``screen_type`` (growth, value, quality),
    then overlays any explicit filter parameters.

    Returns a dict with ``results`` (list of matching companies with
    metrics) and ``meta`` (filter summary).
    """

    # ── Apply presets based on screen_type ────────────────────
    if screen_type == "growth":
        if min_revenue_growth is None:
            min_revenue_growth = 0.15
        if sort_by == "revenue_growth":
            sort_desc = True
    elif screen_type == "value":
        if max_pe is None:
            max_pe = 20.0
        if min_fcf_yield is None:
            min_fcf_yield = 0.03
        if sort_by == "revenue_growth":
            sort_by = "pe_ratio"
            sort_desc = False
    elif screen_type == "quality":
        if min_roe is None:
            min_roe = 0.15
        if min_gross_margin is None:
            min_gross_margin = 0.40
        if sort_by == "revenue_growth":
            sort_by = "roe"
            sort_desc = True

    # ── Subquery: latest annual metric per company ────────────
    latest_year = (
        db.query(
            FinancialMetric.ticker,
            func.max(FinancialMetric.fiscal_year).label("max_year"),
        )
        .filter(FinancialMetric.fiscal_quarter.is_(None))
        .group_by(FinancialMetric.ticker)
        .subquery()
    )

    query = (
        db.query(Company, FinancialMetric)
        .join(FinancialMetric, Company.ticker == FinancialMetric.ticker)
        .join(
            latest_year,
            (FinancialMetric.ticker == latest_year.c.ticker)
            & (FinancialMetric.fiscal_year == latest_year.c.max_year),
        )
        .filter(FinancialMetric.fiscal_quarter.is_(None))
    )

    # ── Apply filters ─────────────────────────────────────────
    if sector:
        query = query.filter(Company.sector.ilike(f"%{sector}%"))
    if min_market_cap:
        query = query.filter(Company.market_cap >= min_market_cap)

    # Growth
    if min_revenue_growth is not None:
        query = query.filter(FinancialMetric.revenue_growth >= min_revenue_growth)
    if max_revenue_growth is not None:
        query = query.filter(FinancialMetric.revenue_growth <= max_revenue_growth)
    if min_eps_growth is not None:
        query = query.filter(FinancialMetric.eps_growth >= min_eps_growth)

    # Value
    if max_pe is not None:
        query = query.filter(FinancialMetric.pe_ratio <= max_pe, FinancialMetric.pe_ratio > 0)
    if min_pe is not None:
        query = query.filter(FinancialMetric.pe_ratio >= min_pe)
    if max_ps is not None:
        query = query.filter(FinancialMetric.ps_ratio <= max_ps)
    if max_ev_ebitda is not None:
        query = query.filter(FinancialMetric.ev_to_ebitda <= max_ev_ebitda, FinancialMetric.ev_to_ebitda > 0)
    if min_fcf_yield is not None:
        query = query.filter(FinancialMetric.fcf_yield >= min_fcf_yield)

    # Quality
    if min_roe is not None:
        query = query.filter(FinancialMetric.roe >= min_roe)
    if min_roic is not None:
        query = query.filter(FinancialMetric.roic >= min_roic)
    if min_gross_margin is not None:
        query = query.filter(FinancialMetric.gross_margin >= min_gross_margin)
    if min_operating_margin is not None:
        query = query.filter(FinancialMetric.operating_margin >= min_operating_margin)
    if min_net_margin is not None:
        query = query.filter(FinancialMetric.net_margin >= min_net_margin)

    # Balance sheet
    if max_debt_to_equity is not None:
        query = query.filter(FinancialMetric.debt_to_equity <= max_debt_to_equity)
    if min_current_ratio is not None:
        query = query.filter(FinancialMetric.current_ratio >= min_current_ratio)

    # Revenue size (from income statements)
    if min_revenue:
        latest_income = (
            db.query(
                IncomeStatement.ticker,
                func.max(IncomeStatement.fiscal_year).label("max_yr"),
            )
            .filter(IncomeStatement.fiscal_quarter.is_(None))
            .group_by(IncomeStatement.ticker)
            .subquery()
        )
        query = query.join(
            IncomeStatement,
            (Company.ticker == IncomeStatement.ticker),
        ).join(
            latest_income,
            (IncomeStatement.ticker == latest_income.c.ticker)
            & (IncomeStatement.fiscal_year == latest_income.c.max_yr),
        ).filter(
            IncomeStatement.fiscal_quarter.is_(None),
            IncomeStatement.revenue >= min_revenue,
        )

    # ── Sort ──────────────────────────────────────────────────
    sort_col = getattr(FinancialMetric, sort_by, FinancialMetric.revenue_growth)
    if sort_desc:
        query = query.order_by(desc(sort_col))
    else:
        query = query.order_by(sort_col)

    rows = query.limit(limit).all()

    # ── Format results ────────────────────────────────────────
    results = []
    for company, metric in rows:
        results.append({
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector,
            "industry": company.industry,
            "market_cap": company.market_cap,
            "fiscal_year": metric.fiscal_year,
            "revenue_growth": _to_float(metric.revenue_growth),
            "eps_growth": _to_float(metric.eps_growth),
            "gross_margin": _to_float(metric.gross_margin),
            "operating_margin": _to_float(metric.operating_margin),
            "net_margin": _to_float(metric.net_margin),
            "roe": _to_float(metric.roe),
            "roic": _to_float(metric.roic),
            "pe_ratio": _to_float(metric.pe_ratio),
            "ps_ratio": _to_float(metric.ps_ratio),
            "ev_to_ebitda": _to_float(metric.ev_to_ebitda),
            "fcf_yield": _to_float(metric.fcf_yield),
            "debt_to_equity": _to_float(metric.debt_to_equity),
            "current_ratio": _to_float(metric.current_ratio),
        })

    filters_applied = {
        k: v
        for k, v in {
            "screen_type": screen_type,
            "min_revenue_growth": min_revenue_growth,
            "max_pe": max_pe,
            "min_fcf_yield": min_fcf_yield,
            "min_roe": min_roe,
            "min_gross_margin": min_gross_margin,
            "sector": sector,
            "sort_by": sort_by,
            "sort_desc": sort_desc,
        }.items()
        if v is not None
    }

    return {
        "count": len(results),
        "limit": limit,
        "filters": filters_applied,
        "results": results,
    }


def _to_float(val) -> float | None:
    """Safely convert a Decimal/Numeric to float."""
    if val is None:
        return None
    return float(val)
