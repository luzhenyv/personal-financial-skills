"""SEC EDGAR API client.

Provides access to:
- Company submissions (filing history)
- XBRL company facts (structured financial data)
- Company tickers lookup (ticker ↔ CIK mapping)
- Filing HTML download (10-K, 10-Q to raw/)
- S&P 500 constituent list

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

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0  # seconds; doubles each retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _headers() -> dict[str, str]:
    return {"User-Agent": settings.sec_user_agent, "Accept": "application/json"}


def _rate_limit() -> None:
    """Respect SEC's 10 requests/second limit."""
    time.sleep(settings.sec_rate_limit)


def _request_with_retry(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = 60,
) -> httpx.Response:
    """Make an HTTP GET request with retry logic for transient errors."""
    hdrs = headers or _headers()
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        _rate_limit()
        try:
            resp = httpx.get(url, headers=hdrs, params=params, timeout=timeout,
                             follow_redirects=True)
            if resp.status_code not in RETRYABLE_STATUS_CODES:
                resp.raise_for_status()
                return resp
            logger.warning(
                f"SEC request returned {resp.status_code}, "
                f"retry {attempt + 1}/{MAX_RETRIES}"
            )
            last_exc = httpx.HTTPStatusError(
                f"HTTP {resp.status_code}", request=resp.request, response=resp
            )
        except httpx.TimeoutException as e:
            logger.warning(f"SEC request timed out, retry {attempt + 1}/{MAX_RETRIES}")
            last_exc = e
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in RETRYABLE_STATUS_CODES:
                raise
            logger.warning(
                f"SEC request returned {e.response.status_code}, "
                f"retry {attempt + 1}/{MAX_RETRIES}"
            )
            last_exc = e

        backoff = RETRY_BACKOFF * (2 ** attempt)
        time.sleep(backoff)

    raise last_exc  # type: ignore[misc]


def pad_cik(cik: str | int) -> str:
    """Pad CIK to 10 digits with leading zeros."""
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
    resp = _request_with_retry(COMPANY_TICKERS_URL)
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
    """Fetch company submission history from SEC."""
    padded = pad_cik(cik)
    url = f"{SUBMISSIONS_URL}/CIK{padded}.json"
    logger.info(f"Fetching submissions for CIK {padded}")
    resp = _request_with_retry(url)
    return resp.json()


def get_recent_filings(
    cik: str, filing_types: list[str] | None = None, limit: int = 20
) -> list[dict]:
    """Get recent filings for a company, optionally filtered by type."""
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

    for i in range(min(len(forms), limit * 5)):
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
    """Fetch XBRL company facts — all US-GAAP taxonomy facts ever reported."""
    padded = pad_cik(cik)
    url = f"{COMPANY_FACTS_URL}/CIK{padded}.json"
    logger.info(f"Fetching company facts for CIK {padded}")
    resp = _request_with_retry(url, timeout=90)
    return resp.json()


def get_company_facts_cached(ticker: str, cik: str) -> dict[str, Any]:
    """Fetch company facts with local file cache (24h TTL)."""
    cache_path = settings.data_dir / "raw" / ticker.upper() / "company_facts.json"

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 24:
            logger.info(f"Using cached company facts for {ticker}")
            with open(cache_path) as f:
                return json.load(f)

    data = get_company_facts(cik)

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


# ──────────────────────────────────────────────
# Filing HTML Download
# ──────────────────────────────────────────────

def download_filing_html(
    cik: str, filing: dict, dest_dir: Path
) -> Path | None:
    """Download a filing's primary HTML document to dest_dir.

    Args:
        cik: Company CIK (unpadded)
        filing: Dict with keys 'accession_number', 'primary_document', 'form', 'report_date'
        dest_dir: Directory to save the file (e.g. data/raw/NVDA/)

    Returns:
        Path to downloaded file, or None on failure.
    """
    acc = filing.get("accession_number", "").replace("-", "")
    doc = filing.get("primary_document", "")
    form = filing.get("form", "")
    report_date = filing.get("report_date", "")[:7].replace("-", "_")

    if not acc or not doc:
        logger.warning("Skipping filing download: missing accession or primary document")
        return None

    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

    suffix = ".htm" if doc.endswith((".htm", ".html")) else Path(doc).suffix or ".htm"
    filename = f"{form.replace('/', '-')}_{report_date}{suffix}"
    out_path = dest_dir / filename

    if out_path.exists():
        logger.info(f"Already downloaded: {out_path.name}")
        return out_path

    dest_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {form} → {out_path.name} ...")

    try:
        resp = _request_with_retry(url, timeout=90)
        out_path.write_bytes(resp.content)
        logger.info(f"  Saved {len(resp.content) / 1024:.0f} KB → {out_path}")
        return out_path
    except Exception as e:
        logger.error(f"  Download failed: {e}")
        return None


# ──────────────────────────────────────────────
# S&P 500 Constituents
# ──────────────────────────────────────────────

_SP500_FALLBACK = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK-B", "TSLA", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "AVGO", "HD", "CVX", "MRK", "ABBV",
    "LLY", "PEP", "KO", "COST", "ADBE", "WMT", "MCD", "CRM", "BAC", "CSCO",
    "TMO", "ACN", "ABT", "DHR", "NFLX", "LIN", "CMCSA", "TXN", "PM", "NEE",
    "WFC", "AMD", "INTC", "QCOM", "UPS", "RTX", "HON", "LOW", "SPGI", "INTU",
]


def get_sp500_tickers() -> list[str]:
    """Return S&P 500 constituent tickers.

    Loads from data/sp500_tickers.json if available,
    otherwise falls back to a curated top-50 subset.
    """
    path = settings.data_dir / "sp500_tickers.json"
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [t.upper() for t in data]
        except Exception:
            pass

    return list(_SP500_FALLBACK)
