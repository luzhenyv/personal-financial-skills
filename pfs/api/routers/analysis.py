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


# ── Signal Aggregation (Fund Manager) ────────────────────────


@router.get("/signals/portfolio/summary")
def get_portfolio_signals(
    portfolio_id: int = Query(1, ge=1),
    lookback_days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
):
    """Aggregate signals for all positions in the portfolio."""
    from pfs.services.signals import aggregate_portfolio_signals

    try:
        return aggregate_portfolio_signals(
            db, portfolio_id, lookback_days=lookback_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/signals/{ticker}")
def get_ticker_signals(
    ticker: str,
    lookback_days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
):
    """Aggregate multi-source signals for a ticker — used by fund-manager skill.

    Combines: price momentum, risk metrics, fundamental metrics into a
    single signal bundle per ticker.
    """
    from pfs.services.signals import aggregate_ticker_signals

    return aggregate_ticker_signals(db, ticker.upper(), lookback_days=lookback_days)


# ── Stock Screening ──────────────────────────────────────────


@router.get("/screen")
def screen_stocks(
    type: str | None = Query(None, description="Preset: growth, value, quality"),
    min_revenue_growth: float | None = Query(None),
    max_revenue_growth: float | None = Query(None),
    min_eps_growth: float | None = Query(None),
    max_pe: float | None = Query(None),
    min_pe: float | None = Query(None),
    max_ps: float | None = Query(None),
    max_ev_ebitda: float | None = Query(None),
    min_fcf_yield: float | None = Query(None),
    min_roe: float | None = Query(None),
    min_roic: float | None = Query(None),
    min_gross_margin: float | None = Query(None),
    min_operating_margin: float | None = Query(None),
    min_net_margin: float | None = Query(None),
    max_debt_to_equity: float | None = Query(None),
    min_current_ratio: float | None = Query(None),
    min_revenue: int | None = Query(None, description="Minimum annual revenue in dollars"),
    min_market_cap: int | None = Query(None),
    sector: str | None = Query(None),
    sort_by: str = Query("revenue_growth"),
    sort_desc: bool = Query(True),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Parameterized stock screening across all ingested companies.

    Use ``type`` for presets (growth, value, quality) or pass individual
    filter parameters.  Used by the idea-generation skill.
    """
    from pfs.services.screen import screen_companies

    return screen_companies(
        db,
        screen_type=type,
        min_revenue_growth=min_revenue_growth,
        max_revenue_growth=max_revenue_growth,
        min_eps_growth=min_eps_growth,
        max_pe=max_pe,
        min_pe=min_pe,
        max_ps=max_ps,
        max_ev_ebitda=max_ev_ebitda,
        min_fcf_yield=min_fcf_yield,
        min_roe=min_roe,
        min_roic=min_roic,
        min_gross_margin=min_gross_margin,
        min_operating_margin=min_operating_margin,
        min_net_margin=min_net_margin,
        max_debt_to_equity=max_debt_to_equity,
        min_current_ratio=min_current_ratio,
        min_revenue=min_revenue,
        min_market_cap=min_market_cap,
        sector=sector,
        sort_by=sort_by,
        sort_desc=sort_desc,
        limit=limit,
    )


# ── Correlation Matrix ───────────────────────────────────────


@router.get("/correlation-matrix")
def get_correlation_matrix(
    tickers: str = Query(..., description="Comma-separated tickers, e.g. NVDA,AAPL,MSFT"),
    lookback_days: int = Query(252, ge=30, le=756),
    db: Session = Depends(get_db),
):
    """Pairwise correlation matrix from daily price returns.

    Used by risk-manager and fund-manager skills for portfolio
    diversification analysis.
    """
    from datetime import date, timedelta

    import numpy as np

    from pfs.services.risk import _price_series, _returns_from_prices

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 tickers")

    end = date.today()
    start = end - timedelta(days=lookback_days + 60)

    # Collect return series per ticker
    returns_map: dict[str, np.ndarray] = {}
    missing: list[str] = []
    for t in ticker_list:
        prices = _price_series(db, t, start, end)
        if len(prices) < 30:
            missing.append(t)
            continue
        returns_map[t] = _returns_from_prices(prices)

    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient price data for: {', '.join(missing)}",
        )

    # Align all series to the shortest length
    valid_tickers = list(returns_map.keys())
    min_len = min(len(r) for r in returns_map.values())
    aligned = np.array([returns_map[t][-min_len:] for t in valid_tickers])

    # Compute correlation matrix
    corr = np.corrcoef(aligned)

    # Build structured response
    matrix: dict[str, dict[str, float]] = {}
    for i, t1 in enumerate(valid_tickers):
        matrix[t1] = {}
        for j, t2 in enumerate(valid_tickers):
            matrix[t1][t2] = round(float(corr[i, j]), 4)

    return {
        "tickers": valid_tickers,
        "lookback_days": lookback_days,
        "trading_days_used": min_len,
        "matrix": matrix,
    }


# ── Knowledge Base (Placeholder) ─────────────────────────────


class KnowledgeIngestRequest(BaseModel):
    title: str
    content: str
    source_type: str = "text"
    sectors: list[str] = []
    tickers_mentioned: list[str] = []
    tags: list[str] = []


@router.post("/knowledge/ingest")
def ingest_knowledge(body: KnowledgeIngestRequest):
    """Placeholder — document ingestion into the knowledge base.

    Full implementation planned. Currently returns a stub response.
    """
    return {
        "status": "placeholder",
        "message": "Knowledge ingestion endpoint not yet implemented. Use the knowledge-base skill scripts directly.",
        "received": {
            "title": body.title,
            "source_type": body.source_type,
            "content_length": len(body.content),
        },
    }
