"""Extract key sections from 10-K HTML filings.

Parses raw 10-K HTML and produces a structured JSON with text from:
  - Item 1  (Business)
  - Item 1A (Risk Factors)
  - Item 7  (MD&A)
  - Item 10 (Directors / Executive Officers)

Output is consumed by the company-profile skill (Task 1: Company Research).

Usage (standalone):
    uv run python -m src.etl.section_extractor NVDA
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from src.config import settings

logger = logging.getLogger(__name__)


def extract_sections(html_path: Path, ticker: str) -> dict:
    """Parse 10-K HTML and extract raw text for key sections.

    Returns a dict of {section_name: raw_text} plus metadata fields.
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

    p1 = find_nth(full_text, r"Item\s+1\.\s*\n?Business\b")
    p1a = find_nth(full_text, r"Item\s+1A\.\s*\n?Risk Factors\b")
    p1b = find_nth(full_text, r"Item\s+1B\.")
    p7 = find_nth(full_text, r"Item\s+7\.\s*\n?Management")
    p7a = find_nth(full_text, r"Item\s+7A\.")
    p10 = find_nth(full_text, r"Item\s+10\.\s*\n?Directors")
    p11 = find_nth(full_text, r"Item\s+11\.")

    def slice_section(start: int, end: int, max_chars: int = 24000) -> str:
        if start < 0:
            return ""
        limit = end if (end and end > start + 50) else start + max_chars
        return full_text[start : min(limit, start + max_chars)].strip()

    sections = {
        "item1_business": slice_section(p1, p1a, 14000),
        "item1a_risk_factors": slice_section(p1a, p1b, 24000),
        "item7_mda": slice_section(p7, p7a, 20000),
        "item10_directors": slice_section(p10, p11, 10000),
        "source_file": html_path.name,
        "ticker": ticker.upper(),
        "total_text_chars": len(full_text),
    }

    logger.info(
        f"  Sections extracted: "
        f"Item1={len(sections['item1_business'])}, "
        f"Item1A={len(sections['item1a_risk_factors'])}, "
        f"Item7={len(sections['item7_mda'])}, "
        f"Item10={len(sections['item10_directors'])} chars"
    )
    return sections


def extract_and_save(ticker: str) -> Path | None:
    """Find the latest 10-K in data/raw/{ticker}/, extract sections, save to profile dir.

    Returns the path to the saved JSON, or None if no 10-K was found.
    """
    ticker = ticker.upper()
    raw_dir = settings.raw_dir / ticker
    profile_dir = settings.ticker_profile_dir(ticker)
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Find the latest 10-K HTML file
    ten_k_files = sorted(raw_dir.glob("10-K_*.htm"), reverse=True) if raw_dir.exists() else []
    if not ten_k_files:
        logger.warning(f"[{ticker}] No 10-K HTML found in {raw_dir}")
        return None

    latest_10k = ten_k_files[0]
    sections = extract_sections(latest_10k, ticker)

    out_path = profile_dir / "10k_raw_sections.json"
    out_path.write_text(json.dumps(sections, indent=2))
    logger.info(f"[{ticker}] Saved → {out_path}")
    return out_path


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Extract 10-K sections for a ticker")
    parser.add_argument("ticker", help="Stock ticker symbol, e.g. NVDA")
    args = parser.parse_args()

    result = extract_and_save(args.ticker)
    if result:
        print(f"Saved: {result}")
    else:
        print(f"No 10-K found for {args.ticker}")
