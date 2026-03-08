"""SEC EDGAR API client.

Provides access to:
- Company submissions (filing history)
- XBRL company facts (structured financial data)
- Company tickers lookup (ticker ↔ CIK mapping)

Rate limited to 10 requests/second per SEC fair-use policy.
Requires User-Agent header with contact email.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# SEC base URLs
SUBMISSIONS_URL = f"{settings.sec_base_url}/submissions"
COMPANY_FACTS_URL = f"{settings.sec_base_url}/api/xbrl/companyfacts"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _headers() -> dict[str, str]:
    return {"User-Agent": settings.sec_user_agent, "Accept": "application/json"}


def _rate_limit() -> None:
    """Respect SEC's 10 requests/second limit."""
    time.sleep(settings.sec_rate_limit)


def pad_cik(cik: str | int) -> str:
    """Pad CIK to 10 digits with leading zeros. SEC API requires CIK0000000000 format."""
    return str(cik).zfill(10)


# ──────────────────────────────────────────────
# Ticker ↔ CIK Resolution
# ──────────────────────────────────────────────

_ticker_cache: dict[str, dict] | None = None


def load_ticker_map() -> dict[str, dict]:
    """Load SEC's ticker-to-CIK mapping. Cached on first call."""
    global _ticker_cache
    if _ticker_cache is not None:
        return _ticker_cache

    cache_path = settings.data_dir / "raw" / "company_tickers.json"

    # Try cached file first (refresh daily)
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 24:
            with open(cache_path) as f:
                data = json.load(f)
            _ticker_cache = {v["ticker"]: v for v in data.values()}
            return _ticker_cache

    # Fetch from SEC
    logger.info("Fetching SEC company tickers...")
    _rate_limit()
    resp = httpx.get(COMPANY_TICKERS_URL, headers=_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Cache to disk
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(data, f)

    _ticker_cache = {v["ticker"]: v for v in data.values()}
    return _ticker_cache


def ticker_to_cik(ticker: str) -> str | None:
    """Resolve ticker symbol to CIK number."""
    ticker_map = load_ticker_map()
    entry = ticker_map.get(ticker.upper())
    if entry:
        return str(entry["cik_str"])
    return None


def ticker_to_company_name(ticker: str) -> str | None:
    """Resolve ticker symbol to company name."""
    ticker_map = load_ticker_map()
    entry = ticker_map.get(ticker.upper())
    if entry:
        return entry.get("title", "")
    return None


# ──────────────────────────────────────────────
# Company Submissions (Filing History)
# ──────────────────────────────────────────────

def get_submissions(cik: str) -> dict[str, Any]:
    """Fetch company submission history from SEC.

    Returns metadata about the company plus list of all filings.
    """
    padded = pad_cik(cik)
    url = f"{SUBMISSIONS_URL}/CIK{padded}.json"
    logger.info(f"Fetching submissions for CIK {padded}")

    _rate_limit()
    resp = httpx.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_recent_filings(
    cik: str, filing_types: list[str] | None = None, limit: int = 20
) -> list[dict]:
    """Get recent filings for a company, optionally filtered by type.

    Args:
        cik: Company CIK number
        filing_types: Filter by filing type, e.g. ['10-K', '10-Q']
        limit: Max number of filings to return
    """
    data = get_submissions(cik)
    recent = data.get("filings", {}).get("recent", {})

    if not recent:
        return []

    filings = []
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    report_dates = recent.get("reportDate", [])

    for i in range(min(len(forms), limit * 5)):  # Over-fetch to handle filtering
        form = forms[i] if i < len(forms) else ""
        if filing_types and form not in filing_types:
            continue

        filing = {
            "form": form,
            "filing_date": dates[i] if i < len(dates) else "",
            "accession_number": accessions[i] if i < len(accessions) else "",
            "primary_document": primary_docs[i] if i < len(primary_docs) else "",
            "report_date": report_dates[i] if i < len(report_dates) else "",
        }
        filings.append(filing)

        if len(filings) >= limit:
            break

    return filings


# ──────────────────────────────────────────────
# Company Facts (XBRL Structured Data)
# ──────────────────────────────────────────────

def get_company_facts(cik: str) -> dict[str, Any]:
    """Fetch XBRL company facts — all reported financial data points.

    This is the primary data source for financial statements.
    Returns a large JSON with all US-GAAP taxonomy facts ever reported.
    """
    padded = pad_cik(cik)
    url = f"{COMPANY_FACTS_URL}/CIK{padded}.json"
    logger.info(f"Fetching company facts for CIK {padded}")

    _rate_limit()
    resp = httpx.get(url, headers=_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()


def get_company_facts_cached(ticker: str, cik: str) -> dict[str, Any]:
    """Fetch company facts with local file cache."""
    cache_path = settings.data_dir / "raw" / ticker.upper() / "company_facts.json"

    # Use cache if less than 1 day old
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 24:
            logger.info(f"Using cached company facts for {ticker}")
            with open(cache_path) as f:
                return json.load(f)

    # Fetch from SEC
    data = get_company_facts(cik)

    # Save to cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(data, f)

    return data


def get_company_metadata(cik: str) -> dict[str, Any]:
    """Extract basic company metadata from submissions API."""
    data = get_submissions(cik)
    return {
        "cik": str(data.get("cik", cik)),
        "name": data.get("name", ""),
        "ticker": ",".join(data.get("tickers", [])),
        "exchanges": data.get("exchanges", []),
        "sic": data.get("sic", ""),
        "sic_description": data.get("sicDescription", ""),
        "fiscal_year_end": data.get("fiscalYearEnd", ""),
        "website": next(
            (w for w in data.get("website", []) if w), ""
        ) if isinstance(data.get("website"), list) else data.get("website", ""),
        "description": data.get("description", ""),
    }
