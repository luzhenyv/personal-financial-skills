"""Analysis routes — tearsheet generation, reports."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.analysis.company_profile import generate_tearsheet, get_profile_data
from src.db.models import AnalysisReport, Company
from src.db.session import get_db

router = APIRouter()


@router.get("/{ticker}/profile")
def get_profile(ticker: str, db: Session = Depends(get_db)):
    """Get structured profile data for a company (JSON)."""
    data = get_profile_data(ticker, session=db)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


@router.post("/{ticker}/tearsheet")
def create_tearsheet(ticker: str, db: Session = Depends(get_db)):
    """Generate a markdown tearsheet for a company.

    Creates/updates the tearsheet in both filesystem and database.
    Returns the markdown content.
    """
    # Check company exists
    company = db.query(Company).filter_by(ticker=ticker.upper()).first()
    if not company:
        raise HTTPException(
            status_code=404,
            detail=f"Company {ticker} not found. POST /api/companies/ingest first.",
        )

    markdown = generate_tearsheet(ticker, session=db, save=True)
    db.commit()
    return {"ticker": ticker.upper(), "markdown": markdown}


@router.get("/{ticker}/tearsheet")
def get_tearsheet(ticker: str, db: Session = Depends(get_db)):
    """Get the most recent tearsheet for a company."""
    report = (
        db.query(AnalysisReport)
        .filter_by(ticker=ticker.upper(), report_type="tearsheet")
        .first()
    )
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No tearsheet for {ticker}. POST /api/analysis/{ticker}/tearsheet to create.",
        )
    return {
        "ticker": ticker.upper(),
        "title": report.title,
        "markdown": report.content_md,
        "file_path": report.file_path,
        "created_at": str(report.created_at),
    }


@router.get("/{ticker}/reports")
def list_reports(ticker: str, db: Session = Depends(get_db)):
    """List all analysis reports for a company."""
    reports = (
        db.query(AnalysisReport)
        .filter_by(ticker=ticker.upper())
        .order_by(AnalysisReport.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "report_type": r.report_type,
            "title": r.title,
            "file_path": r.file_path,
            "generated_by": r.generated_by,
            "created_at": str(r.created_at),
        }
        for r in reports
    ]
