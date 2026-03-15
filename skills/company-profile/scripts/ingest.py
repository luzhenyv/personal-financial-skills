"""
Task 1: Data Ingestion for Company Profile Skill
=================================================
Runs the full ETL pipeline for a given ticker:
  1. Resolve ticker → CIK
  2. Ingest XBRL financial data to PostgreSQL (income, balance, cashflow, metrics)
  3. Download latest 10-K and most recent 10-Q HTML to data/raw/{TICKER}/
  4. Extract raw section text (Item 1, 1A, 7, 10) to data/artifacts/{TICKER}/10k_raw_sections.json

Usage:
    uv run python skills/company-profile/scripts/ingest.py NVDA
    uv run python skills/company-profile/scripts/ingest.py AAPL --years 7

After this script completes, use the raw sections in data/artifacts/{TICKER}/10k_raw_sections.json
to populate the 5 structured JSON files (company_overview, management_team, risk_factors,
competitive_landscape, financial_segments) as part of Task 2.
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Project imports ────────────────────────────────────────────────────────────
from src.etl import sec_client
from src.etl.pipeline import ingest_company


def download_filing(cik: str, filing: dict, dest_dir: Path) -> Path | None:
    """Download a filing's primary HTML document to dest_dir."""
    acc = filing["accession_number"].replace("-", "")
    doc = filing["primary_document"]
    form = filing["form"]
    report_date = filing.get("report_date", "")[:7].replace("-", "_")  # e.g. 2026_01
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

    suffix = ".htm" if doc.endswith((".htm", ".html")) else Path(doc).suffix
    filename = f"{form.replace('/', '-')}_{report_date}{suffix}"
    out_path = dest_dir / filename

    if out_path.exists():
        logger.info(f"Already downloaded: {out_path.name}")
        return out_path

    logger.info(f"Downloading {form} → {out_path.name} ...")
    headers = {"User-Agent": "PersonalFinanceApp stevenlvu@example.com"}
    time.sleep(0.2)  # SEC rate limit
    try:
        resp = httpx.get(url, headers=headers, timeout=90, follow_redirects=True)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        logger.info(f"  Saved {len(resp.content)/1024:.0f} KB → {out_path}")
        return out_path
    except Exception as e:
        logger.error(f"  Download failed: {e}")
        return None


def extract_sections(html_path: Path, ticker: str) -> dict:
    """
    Parse 10-K HTML and extract raw text for:
      - Item 1  (Business)
      - Item 1A (Risk Factors)
      - Item 7  (MD&A)
      - Item 10 (Directors / Executive Officers)

    Returns a dict of {section_name: raw_text}.
    The AI reads this file in Task 2 to create the structured JSON files.
    """
    logger.info(f"Parsing {html_path.name} ...")
    html = html_path.read_bytes()
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(separator="\n", strip=True)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    def find_nth(text: str, pattern: str, n: int = 2) -> int:
        matches = list(re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE))
        idx = n - 1 if len(matches) >= n else len(matches) - 1
        return matches[idx].start() if matches else -1

    p1   = find_nth(full_text, r"Item\s+1\.\s*\n?Business\b")
    p1a  = find_nth(full_text, r"Item\s+1A\.\s*\n?Risk Factors\b")
    p1b  = find_nth(full_text, r"Item\s+1B\.")
    p7   = find_nth(full_text, r"Item\s+7\.\s*\n?Management")
    p7a  = find_nth(full_text, r"Item\s+7A\.")
    p10  = find_nth(full_text, r"Item\s+10\.\s*\n?Directors")
    p11  = find_nth(full_text, r"Item\s+11\.")

    def slice_section(start: int, end: int, max_chars: int = 24000) -> str:
        if start < 0:
            return ""
        limit = end if (end and end > start + 50) else start + max_chars
        return full_text[start : min(limit, start + max_chars)].strip()

    sections = {
        "item1_business":          slice_section(p1, p1a, 14000),
        "item1a_risk_factors":     slice_section(p1a, p1b, 24000),
        "item7_mda":               slice_section(p7, p7a, 20000),
        "item10_directors":        slice_section(p10, p11, 10000),
        "source_file":             html_path.name,
        "ticker":                  ticker.upper(),
        "total_text_chars":        len(full_text),
    }

    logger.info(
        f"  Sections extracted: "
        f"Item1={len(sections['item1_business'])}, "
        f"Item1A={len(sections['item1a_risk_factors'])}, "
        f"Item7={len(sections['item7_mda'])}, "
        f"Item10={len(sections['item10_directors'])} chars"
    )
    return sections


def main():
    parser = argparse.ArgumentParser(description="Task 1: Ingest company data")
    parser.add_argument("ticker", help="Stock ticker symbol, e.g. NVDA")
    parser.add_argument("--years", type=int, default=5, help="Years of historical data to load (default: 5)")
    parser.add_argument("--quarterly", action="store_true", help="Also load quarterly statements")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    raw_dir = Path(f"data/raw/{ticker}")
    processed_dir = Path(f"data/artifacts/{ticker}")
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: XBRL → PostgreSQL ──────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"STEP 1: Ingesting XBRL financial data for {ticker}")
    logger.info(f"{'='*60}")
    result = ingest_company(ticker, years=args.years, include_quarterly=args.quarterly, include_prices=True)

    logger.info(f"\nIngestion result:")
    for k, v in result.items():
        if k != "errors":
            logger.info(f"  {k}: {v}")
    if result["errors"]:
        logger.warning(f"  Errors ({len(result['errors'])}):")
        for e in result["errors"]:
            logger.warning(f"    - {e}")

    # ── Step 2: Resolve CIK (needed for filing URLs) ───────────────────────────
    cik = sec_client.ticker_to_cik(ticker)
    if not cik:
        logger.error(f"Could not resolve CIK for {ticker}")
        return

    # ── Step 3: Download 10-K and most recent 10-Q ────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"STEP 2: Downloading filings for {ticker} (CIK {cik})")
    logger.info(f"{'='*60}")

    filings = sec_client.get_recent_filings(cik, ["10-K", "10-Q"], limit=10)
    logger.info(f"Found {len(filings)} filings")

    # Take latest 10-K and latest 10-Q
    latest_10k = next((f for f in filings if f["form"] == "10-K"), None)
    latest_10q = next((f for f in filings if f["form"] == "10-Q"), None)

    downloaded_paths = []
    for filing in [f for f in [latest_10k, latest_10q] if f]:
        path = download_filing(cik, filing, raw_dir)
        if path:
            downloaded_paths.append((filing["form"], path))

    # ── Step 4: Extract raw sections from latest 10-K ─────────────────────────
    sections_path = processed_dir / "10k_raw_sections.json"
    if latest_10k:
        form_name = latest_10k["form"]
        ten_k_path = next((p for form, p in downloaded_paths if form == "10-K"), None)
        if ten_k_path and ten_k_path.exists():
            logger.info(f"\n{'='*60}")
            logger.info(f"STEP 3: Extracting 10-K sections for {ticker}")
            logger.info(f"{'='*60}")
            sections = extract_sections(ten_k_path, ticker)
            sections["filing_date"] = latest_10k.get("filing_date", "")
            sections["report_date"] = latest_10k.get("report_date", "")
            sections_path.write_text(json.dumps(sections, indent=2))
            logger.info(f"  Saved → {sections_path}")

    # ── Summary ────────────────────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"TASK 1 COMPLETE: {ticker}")
    logger.info(f"{'='*60}")
    logger.info(f"  Raw files  : {list(raw_dir.iterdir())}")
    logger.info(f"  Artifacts  : {sections_path} ({'exists' if sections_path.exists() else 'MISSING'})")
    logger.info(f"  DB records : income={result['income_statements']}, "
                f"bs={result['balance_sheets']}, cf={result['cash_flow_statements']}, "
                f"metrics={result['financial_metrics']}")
    logger.info(f"\nNEXT STEP (Task 2): Read {sections_path} and populate:")
    logger.info(f"  data/artifacts/{ticker}/company_overview.json")
    logger.info(f"  data/artifacts/{ticker}/management_team.json")
    logger.info(f"  data/artifacts/{ticker}/risk_factors.json")
    logger.info(f"  data/artifacts/{ticker}/competitive_landscape.json")
    logger.info(f"  data/artifacts/{ticker}/financial_segments.json")
    logger.info(f"  data/artifacts/{ticker}/investment_thesis.json")


if __name__ == "__main__":
    main()
