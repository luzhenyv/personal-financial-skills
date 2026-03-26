"""Filing data service — SEC filing retrieval and content serving."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from pfs.config import settings
from pfs.db.models import SecFiling
from pfs.services.companies import _row_to_dict, require_company


def _local_filing_path(ticker: str, filing: SecFiling) -> Path | None:
    """Reconstruct the local file path for a downloaded filing."""
    if not filing.filing_type or not filing.reporting_date:
        return None
    report_date = filing.reporting_date.strftime("%Y_%m")
    form = filing.filing_type.replace("/", "-")
    filename = f"{form}_{report_date}.htm"
    return settings.raw_dir / ticker / filename


def list_filings(
    db: Session,
    ticker: str,
    *,
    form_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return SEC filings for *ticker* with optional form type filter."""
    ticker = ticker.upper()
    require_company(db, ticker)
    q = db.query(SecFiling).filter(SecFiling.ticker == ticker)
    if form_type:
        q = q.filter(SecFiling.filing_type == form_type)
    rows = q.order_by(SecFiling.filing_date.desc()).all()

    results = []
    for r in rows:
        d = _row_to_dict(r)
        local = _local_filing_path(ticker, r)
        d["local_path"] = str(local) if local and local.exists() else None
        results.append(d)
    return results


def get_filing(db: Session, ticker: str, filing_id: int) -> dict[str, Any] | None:
    """Return a single SEC filing by ID, or ``None``."""
    ticker = ticker.upper()
    row = (
        db.query(SecFiling)
        .filter(SecFiling.id == filing_id, SecFiling.ticker == ticker)
        .first()
    )
    if not row:
        return None
    d = _row_to_dict(row)
    local = _local_filing_path(ticker, row)
    d["local_path"] = str(local) if local and local.exists() else None
    return d


def get_filing_content(db: Session, ticker: str, filing_id: int) -> tuple[str, bytes] | None:
    """Return (media_type, content_bytes) for a filing, or ``None``.

    Tries local file first, then proxies from SEC EDGAR.
    Returns ``None`` if the filing is not found.
    Raises ``RuntimeError`` if SEC EDGAR proxy fails.
    """
    ticker = ticker.upper()
    row = (
        db.query(SecFiling)
        .filter(SecFiling.id == filing_id, SecFiling.ticker == ticker)
        .first()
    )
    if not row:
        return None

    # 1. Local file
    local = _local_filing_path(ticker, row)
    if local and local.exists():
        return "text/html", local.read_bytes()

    # 2. SEC EDGAR proxy
    if row.primary_doc_url:
        from pfs.etl.sec_client import _request_with_retry

        resp = _request_with_retry(row.primary_doc_url, timeout=90)
        return "text/html", resp.content

    return None
