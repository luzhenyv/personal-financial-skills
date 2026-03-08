"""Company routes — CRUD for companies, ETL triggers."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db.models import Company, Watchlist
from src.db.session import get_db
from src.etl.pipeline import ingest_company

router = APIRouter()


class IngestRequest(BaseModel):
    ticker: str
    years: int = 5
    include_prices: bool = True


class IngestResponse(BaseModel):
    ticker: str
    company: bool
    income_statements: int
    balance_sheets: int
    cash_flow_statements: int
    financial_metrics: int
    sec_filings: int
    daily_prices: int
    errors: list[str]


class CompanyResponse(BaseModel):
    ticker: str
    name: str
    cik: str
    sector: str | None
    industry: str | None
    exchange: str | None
    sic_code: str | None
    description: str | None
    website: str | None
    market_cap: int | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[CompanyResponse])
def list_companies(db: Session = Depends(get_db)):
    """List all companies in the database."""
    companies = db.query(Company).order_by(Company.ticker).all()
    return companies


@router.get("/{ticker}", response_model=CompanyResponse)
def get_company(ticker: str, db: Session = Depends(get_db)):
    """Get a single company by ticker."""
    company = db.query(Company).filter_by(ticker=ticker.upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
    return company


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest, db: Session = Depends(get_db)):
    """Trigger ETL pipeline for a company.

    Fetches data from SEC EDGAR, parses XBRL, stores in PostgreSQL.
    """
    result = ingest_company(
        ticker=req.ticker,
        years=req.years,
        include_prices=req.include_prices,
        session=db,
    )
    return IngestResponse(**result)


@router.post("/ingest-batch")
def ingest_batch(tickers: list[str], db: Session = Depends(get_db)):
    """Ingest multiple companies."""
    results = []
    for ticker in tickers:
        result = ingest_company(ticker=ticker, years=5, include_prices=False, session=db)
        results.append(result)
    return results


@router.get("/{ticker}/watchlist")
def get_watchlist_status(ticker: str, db: Session = Depends(get_db)):
    """Check if a company is on the watchlist."""
    entry = db.query(Watchlist).filter_by(ticker=ticker.upper(), is_active=True).first()
    if entry:
        return {
            "on_watchlist": True,
            "category": entry.category,
            "thesis": entry.thesis,
            "target_price": float(entry.target_price) if entry.target_price else None,
        }
    return {"on_watchlist": False}
