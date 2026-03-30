"""Analysis API router — exposes heavy-compute endpoints.

These endpoints wrap the ``pfs.services`` modules so that skill scripts
and the dashboard can call them over HTTP instead of importing platform
modules directly.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pfs.api.deps import get_db

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/profile/{ticker}")
def get_profile(ticker: str, years: int = Query(7)):
    """Return all DB data needed for the Company Profile page."""
    from pfs.services.analysis import get_profile_data

    return get_profile_data(ticker.upper(), years)


@router.get("/valuation/{ticker}")
def get_valuation(
    ticker: str,
    revenue_growth: float | None = Query(None),
    wacc: float | None = Query(None),
):
    """Run a full DCF + scenario + comps valuation."""
    from pfs.services.valuation import valuation_summary

    overrides: dict = {}
    if revenue_growth is not None:
        overrides["revenue_growth"] = revenue_growth
    if wacc is not None:
        overrides["wacc"] = wacc

    result = valuation_summary(ticker.upper(), **overrides)
    return asdict(result)


@router.get("/comps/{ticker}")
def get_comps(
    ticker: str,
    peers: str | None = Query(None, description="Comma-separated peer tickers"),
    refresh: bool = Query(False),
):
    """Build comparable company analysis table with caching."""
    from pfs.services.comps import build_comps

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
    from pfs.services.analysis import generate_tearsheet

    md = generate_tearsheet(ticker.upper())
    return {"ticker": ticker.upper(), "markdown": md}


@router.post("/investment-report/{ticker}")
def generate_report(
    ticker: str,
    revenue_growth: float | None = Query(None),
    wacc: float | None = Query(None),
):
    """Generate a comprehensive investment report (heavy)."""
    from pfs.services.investment_report import generate_investment_report

    kwargs: dict = {}
    if revenue_growth is not None:
        kwargs["revenue_growth"] = revenue_growth
    if wacc is not None:
        kwargs["wacc"] = wacc

    md = generate_investment_report(ticker.upper(), save=True, **kwargs)
    return {"ticker": ticker.upper(), "markdown": md}


class ReportUpsert(BaseModel):
    ticker: str
    report_type: str
    title: str | None = None
    content_md: str
    file_path: str | None = None
    generated_by: str = "agent"


@router.post("/reports")
def upsert_report(body: ReportUpsert):
    """Upsert an analysis report into the database.

    If a report with the same ticker + report_type already exists, it is
    updated.  Otherwise a new row is created.
    """
    from pfs.api.deps import get_db as _get_db_gen
    from pfs.db.models import AnalysisReport

    db = next(_get_db_gen())
    try:
        existing = (
            db.query(AnalysisReport)
            .filter(
                AnalysisReport.ticker == body.ticker.upper(),
                AnalysisReport.report_type == body.report_type,
            )
            .first()
        )
        if existing:
            existing.title = body.title
            existing.content_md = body.content_md
            existing.file_path = body.file_path
            existing.generated_by = body.generated_by
        else:
            row = AnalysisReport(
                ticker=body.ticker.upper(),
                report_type=body.report_type,
                title=body.title,
                content_md=body.content_md,
                file_path=body.file_path,
                generated_by=body.generated_by,
            )
            db.add(row)
        db.commit()
        return {"status": "ok", "ticker": body.ticker.upper(), "report_type": body.report_type}
    finally:
        db.close()


# ── Risk Analytics ───────────────────────────────────────────


@router.post("/risk/portfolio")
def compute_portfolio_risk(
    portfolio_id: int = Query(1, ge=1),
    benchmark: str = Query("SPY"),
    lookback_days: int = Query(252, ge=30, le=756),
    db: Session = Depends(get_db),
):
    """Compute portfolio-level risk: beta, VaR, Sharpe, Sortino, drawdown, correlation."""
    from pfs.services.risk import portfolio_risk

    try:
        return portfolio_risk(db, portfolio_id, benchmark=benchmark, lookback_days=lookback_days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/risk/{ticker}")
def compute_ticker_risk(
    ticker: str,
    benchmark: str = Query("SPY"),
    lookback_days: int = Query(252, ge=30, le=756),
    db: Session = Depends(get_db),
):
    """Per-ticker risk metrics: beta, volatility, correlation, Sharpe, drawdown."""
    from pfs.services.risk import ticker_risk

    return ticker_risk(db, ticker.upper(), benchmark=benchmark, lookback_days=lookback_days)
