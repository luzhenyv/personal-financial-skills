"""Deterministic 10-K field extraction for company-profile Task 1.

Parses ``10k_raw_sections.json`` (produced by the ETL section_extractor) and
the REST API to pre-populate structured JSON skeletons for Task 1.  The agent
then enhances them with narrative/qualitative content.

Deterministically extracted:
  - Executive officers (name, title, age, prior roles) from Item 1 / Item 10
  - Revenue segments from REST API ``GET /api/financials/{TICKER}/segments``
  - Risk factor titles and categories from Item 1A (structured headings)
  - Company metadata from REST API ``GET /api/companies/{TICKER}``

Output:
  data/artifacts/{TICKER}/profile/
    management_team_skeleton.json
    financial_segments_skeleton.json
    risk_factors_skeleton.json
    company_overview_skeleton.json

The agent reads these skeletons, enriches them, and saves the final
``management_team.json``, ``financial_segments.json``, etc.

Usage:
    uv run python skills/company-profile/scripts/extract_10k.py NVDA
    uv run python skills/company-profile/scripts/extract_10k.py AAPL --api-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

API_URL = os.environ.get("PFS_API_URL", "http://localhost:8000")


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    data.setdefault("schema_version", "1.0")
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"  Saved → {path}")


def api_get(endpoint: str, params: dict | None = None) -> Any:
    """Call a REST API endpoint, return parsed JSON or None on error."""
    url = f"{API_URL}{endpoint}"
    try:
        resp = httpx.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        print(f"  API {resp.status_code} for {endpoint}")
    except httpx.HTTPError as e:
        print(f"  API error for {endpoint}: {e}")
    return None


# ── Executive extraction ───────────────────────────────────────────────────────

_EXEC_HEADER_RE = re.compile(
    r"(?:Information About Our Executive Officers|"
    r"Executive Officers of the Registrant|"
    r"Identification of Executive Officers)",
    re.IGNORECASE,
)

_EXEC_TABLE_RE = re.compile(
    r"^(?P<name>[A-Z][a-zA-Z\.\-\' ]+?)\s+"
    r"(?P<age>\d{2,3})\s+"
    r"(?P<title>.+)$",
    re.MULTILINE,
)

_EXEC_BIO_RE = re.compile(
    r"^(?P<name>[A-Z][a-zA-Z\.\-\' ]+?)\s+"
    r"(?:co-founded|joined|has served|was appointed|became|serves)",
    re.MULTILINE,
)


def _extract_executives(sections: dict) -> list[dict]:
    """Parse executive officers from Item 1 / Item 10 text."""
    # Executive info may appear in Item 1 (after "Information About Our Executive Officers")
    # or in Item 10 (which often just references Item 1)
    text = sections.get("item1_business", "") + "\n" + sections.get("item10_directors", "")

    # Find the executive officers section
    header_match = _EXEC_HEADER_RE.search(text)
    if not header_match:
        return []

    exec_text = text[header_match.start():]

    # Extract from tabular format: Name  Age  Title
    table_matches = list(_EXEC_TABLE_RE.finditer(exec_text[:3000]))

    executives: list[dict] = []
    seen_names: set[str] = set()

    for m in table_matches:
        name = m.group("name").strip()
        age_str = m.group("age").strip()
        title = m.group("title").strip()

        # Filter out false positives
        if len(name) < 5 or len(name) > 40:
            continue
        if not title or len(title) < 3:
            continue
        try:
            age = int(age_str)
            if age < 25 or age > 100:
                continue
        except ValueError:
            continue

        if name in seen_names:
            continue
        seen_names.add(name)

        executives.append({
            "name": name,
            "title": title,
            "age": age,
            "prior_roles": [],
            "accomplishments": "",
            "insider_ownership_pct": "",
        })

    # Enrich with bio text
    for exec_info in executives:
        pattern = re.compile(
            re.escape(exec_info["name"].split()[-1]) + r"\b",
            re.IGNORECASE,
        )
        bio_matches = list(pattern.finditer(exec_text))
        for bm in bio_matches:
            # Grab the paragraph around this mention (after the table section)
            start = max(bm.start() - 20, 0)
            end = min(bm.start() + 2000, len(exec_text))
            para = exec_text[start:end]

            # Extract prior roles: "Prior to NVIDIA" or "From YEAR to YEAR"
            prior_roles = re.findall(
                r"(?:prior to|from \d{4} to \d{4})[^.]*?(?:at|with) ([A-Z][A-Za-z &,]+)",
                para, re.IGNORECASE,
            )
            if prior_roles:
                exec_info["prior_roles"] = list(dict.fromkeys(prior_roles))[:5]
                break

    return executives


# ── Risk factor extraction ─────────────────────────────────────────────────────

_RISK_CATEGORY_RE = re.compile(
    r"^Risks?\s+Related\s+to\s+(.+?)$",
    re.MULTILINE | re.IGNORECASE,
)

_RISK_TITLE_RE = re.compile(
    r"^([A-Z][A-Za-z,\-\' ]+(?:may|could|has|have|is|are|will|would|should|might|can)"
    r"[^.]{10,120}\.?)$",
    re.MULTILINE,
)


def _extract_risk_factors(sections: dict) -> list[dict]:
    """Parse risk factor headings from Item 1A text."""
    text = sections.get("item1a_risk_factors", "")
    if not text:
        return []

    # First pass: find category headers
    categories = list(_RISK_CATEGORY_RE.finditer(text))

    # Build category ranges
    cat_ranges: list[tuple[str, int, int]] = []
    for i, m in enumerate(categories):
        cat_name = m.group(1).strip().rstrip(".")
        start = m.end()
        end = categories[i + 1].start() if i + 1 < len(categories) else len(text)
        cat_ranges.append((cat_name, start, end))

    # If no structured categories found, use the summary bullets
    risks: list[dict] = []

    if cat_ranges:
        for cat_name, start, end in cat_ranges:
            section_text = text[start:end]
            # Find risk factor titles (sentences that are standalone headings)
            titles = _RISK_TITLE_RE.findall(section_text)
            for title in titles[:6]:  # cap per category
                title = title.strip()
                if len(title) < 20 or len(title) > 200:
                    continue
                risks.append({
                    "category": _normalize_category(cat_name),
                    "title": title,
                    "description": "",  # AI fills this
                })
    else:
        # Fallback: bullet-point summary
        bullets = re.findall(r"[•\u2022]\s*(.+?)(?:\n|$)", text[:5000])
        for b in bullets[:12]:
            risks.append({
                "category": "General",
                "title": b.strip(),
                "description": "",
            })

    return risks[:12]


def _normalize_category(raw: str) -> str:
    """Map verbose category names to standard 4 categories."""
    lower = raw.lower()
    if "industry" in lower or "market" in lower:
        return "Industry/Market"
    if "demand" in lower or "supply" in lower or "manufactur" in lower:
        return "Company-Specific"
    if "global" in lower or "operat" in lower:
        return "Company-Specific"
    if "regulat" in lower or "legal" in lower or "stock" in lower:
        return "Macro"
    if "financial" in lower or "tax" in lower:
        return "Financial"
    return "Company-Specific"


# ── Revenue segments from API ──────────────────────────────────────────────────

def _fetch_segments(ticker: str) -> dict:
    """Fetch revenue segments from the REST API and structure them."""
    data = api_get(f"/api/financials/{ticker}/segments")
    if not data:
        return {}

    # Group by fiscal year
    by_year: dict[int, list] = {}
    for row in data:
        fy = row.get("fiscal_year")
        if fy:
            by_year.setdefault(fy, []).append(row)

    if not by_year:
        return {}

    latest_fy = max(by_year)
    prior_fy = latest_fy - 1 if (latest_fy - 1) in by_year else None

    segments: list[dict] = []
    for row in by_year[latest_fy]:
        seg: dict = {
            "name": row.get("segment_name", ""),
            "segment_type": row.get("segment_type", ""),
            "revenue_fy_b": round(float(row.get("revenue", 0)) / 1e9, 2) if row.get("revenue") else None,
            "description": "",
        }

        # Find prior year match for YoY growth
        if prior_fy:
            for prior_row in by_year.get(prior_fy, []):
                if prior_row.get("segment_name") == seg["name"]:
                    prior_rev = float(prior_row.get("revenue", 0))
                    if prior_rev > 0 and seg["revenue_fy_b"]:
                        current_rev = seg["revenue_fy_b"] * 1e9
                        seg["revenue_prior_fy_b"] = round(prior_rev / 1e9, 2)
                        seg["yoy_growth_pct"] = round((current_rev / prior_rev - 1) * 100, 1)
                    break

        segments.append(seg)

    return {
        "fiscal_year": latest_fy,
        "segments": segments,
    }


# ── Company metadata from API ─────────────────────────────────────────────────

def _fetch_company_metadata(ticker: str) -> dict:
    """Fetch company metadata from REST API."""
    data = api_get(f"/api/companies/{ticker}")
    if not data:
        return {}
    return {
        "ticker": ticker,
        "company_name": data.get("name", ""),
        "cik": data.get("cik", ""),
        "sector": data.get("sector", ""),
        "industry": data.get("industry", ""),
        "exchange": data.get("exchange", ""),
        "fiscal_year_end": data.get("fiscal_year_end", ""),
        "description": data.get("description", ""),
        "website": data.get("website", ""),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract structured fields from 10-K sections and REST API"
    )
    parser.add_argument("ticker", help="Stock ticker, e.g. NVDA")
    parser.add_argument("--api-url", default=None, help="Override PFS_API_URL")
    args = parser.parse_args()

    global API_URL
    if args.api_url:
        API_URL = args.api_url

    ticker = args.ticker.upper()
    profile_dir = Path(f"data/artifacts/{ticker}/profile")
    profile_dir.mkdir(parents=True, exist_ok=True)

    sections_path = profile_dir / "10k_raw_sections.json"
    sections = load_json(sections_path)
    if not sections:
        print(f"No 10k_raw_sections.json found for {ticker}.")
        print(f"Run: uv run python -m pfs.etl.section_extractor {ticker}")
        return

    print(f"Extracting structured fields for {ticker}...")

    # 1. Executives
    executives = _extract_executives(sections)
    if executives:
        save_json(profile_dir / "management_team_skeleton.json", {
            "ticker": ticker,
            "source": f"10-K {sections.get('source_file', '')} Item 1 / Item 10",
            "executives": executives,
            "board": {"size": None, "independent_directors": None, "notable_members": []},
            "governance_notes": "",
        })
        print(f"  Found {len(executives)} executives")
    else:
        print("  No executives found in 10-K text")

    # 2. Risk factors
    risks = _extract_risk_factors(sections)
    if risks:
        save_json(profile_dir / "risk_factors_skeleton.json", {
            "ticker": ticker,
            "source": f"10-K {sections.get('source_file', '')} Item 1A",
            "risks": risks,
        })
        print(f"  Found {len(risks)} risk factor headings")
    else:
        print("  No risk factors extracted")

    # 3. Revenue segments from API
    seg_data = _fetch_segments(ticker)
    if seg_data.get("segments"):
        save_json(profile_dir / "financial_segments_skeleton.json", {
            "ticker": ticker,
            "source": f"REST API + 10-K MD&A",
            "fiscal_year": seg_data["fiscal_year"],
            "segments": seg_data["segments"],
            "geographic_revenue_fy": {},
        })
        print(f"  Found {len(seg_data['segments'])} revenue segments")
    else:
        print("  No segment data from API")

    # 4. Company overview skeleton
    meta = _fetch_company_metadata(ticker)
    if meta:
        save_json(profile_dir / "company_overview_skeleton.json", {
            **meta,
            "source": f"REST API + 10-K {sections.get('source_file', '')} Item 1",
            "fiscal_year": None,
            "business_overview": "",
            "revenue_model": "",
            "customers": "",
            "segments": seg_data.get("segments", []),
            "products": [],
            "geographic_revenue": {},
        })
        print(f"  Company metadata: {meta.get('company_name', ticker)}")
    else:
        print("  No company metadata from API")

    print(f"\n✓ Skeletons written to {profile_dir}/")
    print("  The agent should read *_skeleton.json files, enrich with AI, and save final versions.")


if __name__ == "__main__":
    main()
