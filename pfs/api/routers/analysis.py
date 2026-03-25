"""Analysis API router — exposes heavy-compute endpoints.

These endpoints wrap the ``pfs.analysis`` modules so that skill scripts
and the dashboard can call them over HTTP instead of importing platform
modules directly.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/profile/{ticker}")
def get_profile(ticker: str, years: int = Query(7)):
    """Return all DB data needed for the Company Profile page."""
    from pfs.analysis.company_profile import get_profile_data

    return get_profile_data(ticker.upper(), years)


@router.get("/valuation/{ticker}")
def get_valuation(
    ticker: str,
    revenue_growth: float | None = Query(None),
    wacc: float | None = Query(None),
):
    """Run a full DCF + scenario + comps valuation."""
    from pfs.analysis.valuation import valuation_summary

    overrides: dict = {}
    if revenue_growth is not None:
        overrides["revenue_growth"] = revenue_growth
    if wacc is not None:
        overrides["wacc"] = wacc

    result = valuation_summary(ticker.upper(), **overrides)
    return asdict(result)


@router.get("/coverage/{ticker}")
def get_coverage(ticker: str):
    """Run ETL coverage analysis for a single company."""
    from skills.etl_coverage.scripts.check_coverage import analyze_company

    return analyze_company(ticker.upper())


@router.get("/comps/{ticker}")
def get_comps(
    ticker: str,
    peers: str | None = Query(None, description="Comma-separated peer tickers"),
    refresh: bool = Query(False),
):
    """Build comparable company analysis table with caching."""
    from pfs.analysis.comps import build_comps

    peers_list = [p.strip().upper() for p in peers.split(",") if p.strip()] if peers else None
    return build_comps(ticker.upper(), peers_override=peers_list, force_refresh=refresh)


@router.get("/current-price/{ticker}")
def get_current_price(ticker: str):
    """Return the latest price via yfinance."""
    from pfs.etl.yfinance_client import get_current_price as _get_price

    price = _get_price(ticker.upper())
    if price is None:
        return JSONResponse(status_code=404, content={"error": "Price not available"})
    return {"ticker": ticker.upper(), "price": price}


@router.get("/tearsheet/{ticker}")
def get_tearsheet(ticker: str):
    """Generate a concise markdown tearsheet."""
    from pfs.analysis.company_profile import generate_tearsheet

    md = generate_tearsheet(ticker.upper())
    return {"ticker": ticker.upper(), "markdown": md}


@router.post("/investment-report/{ticker}")
def generate_report(
    ticker: str,
    revenue_growth: float | None = Query(None),
    wacc: float | None = Query(None),
):
    """Generate a comprehensive investment report (heavy)."""
    from pfs.analysis.investment_report import generate_investment_report

    kwargs: dict = {}
    if revenue_growth is not None:
        kwargs["revenue_growth"] = revenue_growth
    if wacc is not None:
        kwargs["wacc"] = wacc

    md = generate_investment_report(ticker.upper(), save=True, **kwargs)
    return {"ticker": ticker.upper(), "markdown": md}
