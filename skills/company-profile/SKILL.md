---
name: company-profile
description: Generate a comprehensive company profile report for a US public company through a 4-task workflow — (1) data ingestion from SEC 10-K/Q filings, yfinance, and web search, (2) company research including management, competitive landscape, and risks, (3) financial analysis with comparable companies, (4) report generation. Raw filings saved to data/raw/{ticker}/, processed data to data/processed/{ticker}/, structured data to PostgreSQL.
---

# Company Profile

Generate a comprehensive company profile report through a structured 4-task workflow. Each task builds on prior outputs.

## Overview

This skill produces company profile reports sourced primarily from **SEC 10-K/Q filings** (the authoritative source), supplemented by yfinance and web search. The output includes management team analysis, competitive landscape, comparable company analysis, and risks/opportunities extracted from actual filings.

**Data Flow**:
```
SEC EDGAR (10-K/Q HTML) → data/raw/{ticker}/
Raw section text       → data/processed/{ticker}/10k_raw_sections.json
AI-parsed structured   → data/processed/{ticker}/*.json
Structured financials  → PostgreSQL (via XBRL ETL)
Report                 → data/reports/{ticker}/company_profile.md + analysis_reports table
Interactive view       → Streamlit app at http://localhost:8501
```

**Data Source Priority & Conflict Resolution**:

| Priority | Source | Used For |
|----------|--------|----------|
| 1 (Primary) | SEC EDGAR (10-K/Q XBRL + HTML) | All financial statements, revenue, margins, EPS, balance sheet |
| 2 (Secondary) | yfinance | Market data (price, market cap, P/E fwd), peer discovery, LTM estimates |
| 3 (Backup) | Alpha Vantage (`ALPHA_VANTAGE_KEY`) | Use when SEC XBRL and yfinance figures conflict or data is missing |

When a conflict is detected between primary and secondary sources (e.g., revenue figures differ by >2%), fall back to **Alpha Vantage** to obtain a third reference point and use the majority-consensus value. Log the discrepancy as a footnote in the report.

```python
# Example: resolve conflict using Alpha Vantage as tiebreaker
from src.etl.alpha_vantage_client import get_income_statement  # if implemented

sec_revenue = 130.5e9      # from XBRL
yfinance_revenue = 128.0e9 # from yfinance
av_revenue = get_income_statement(ticker)["annualReports"][0]["totalRevenue"]

# Use the value that two sources agree on (within 2% tolerance)
```

> **Note**: Alpha Vantage free tier is limited to **25 requests/day**. Reserve it for conflict resolution only, not bulk ingestion.

**Stock Split Adjustment (Per-Share Metrics)**:

SEC XBRL filings report EPS and other per-share figures **as-filed at the time of the original filing** — they are NOT retroactively restated for subsequent stock splits. This causes historical per-share metrics to appear inflated relative to post-split values (e.g., NVDA reported FY2024 EPS of $11.93 pre-split, which should be $1.19 after the 10:1 split in June 2024).

**Mandatory adjustment rule**: All per-share metrics displayed in the report and Streamlit app **must be split-adjusted to the current share basis** so that multi-year trends are comparable. This applies to:
- EPS (basic and diluted)
- Dividends per share
- Book value per share
- Any custom per-share ratios

**How to detect and apply splits**:
1. **Query yfinance for split history**: `yf.Ticker(ticker).splits` returns a series of split dates and ratios
2. **Compute cumulative split factor**: For each historical fiscal year, multiply all split ratios that occurred *after* that fiscal year's end date up to the present
3. **Adjust**: `adjusted_eps = reported_eps / cumulative_split_factor`
4. **Store the split history** in `data/processed/{TICKER}/stock_splits.json` for auditability

```python
# Example: adjust historical EPS for NVDA (10:1 split on 2024-06-10)
import yfinance as yf

splits = yf.Ticker("NVDA").splits  # e.g., {2024-06-10: 10.0, 2021-07-20: 4.0}

# For FY2024 (ended Jan 2024, before the June 2024 split):
# cumulative_factor = 10.0 (one split after FY-end)
# adjusted_eps = 11.93 / 10.0 = 1.193 ≈ $1.19

# For FY2021 (ended Jan 2021, before both splits):
# cumulative_factor = 4.0 * 10.0 = 40.0
# adjusted_eps = reported_eps / 40.0
```

> **Important**: Shares outstanding (`shares_diluted`) from XBRL are also as-reported. When computing per-share metrics from raw financials (e.g., `net_income / shares_diluted`), either adjust both numerator consistency or use the already-adjusted EPS. The safest approach is to adjust shares outstanding upward by the same cumulative split factor and recompute derived metrics.

```json
// data/processed/{TICKER}/stock_splits.json
{
  "ticker": "NVDA",
  "splits": [
    { "date": "2024-06-10", "ratio": 10, "description": "10-for-1 stock split" },
    { "date": "2021-07-20", "ratio": 4, "description": "4-for-1 stock split" }
  ],
  "source": "yfinance",
  "current_basis_date": "2026-03-09"
}
```

---

**Scripts** (in `skills/company-profile/scripts/`):

| Script | Purpose | Task |
|--------|---------|------|
| `ingest.py {TICKER}` | XBRL→DB + download 10-K/Q + extract raw section text | 1 |
| `build_comps.py {TICKER}` | Build comparable company table via yfinance | 3 |
| `generate_report.py {TICKER}` | Assemble final markdown report from all JSON + DB | 4 |

---

## Trigger

User asks for company overview, profile, tearsheet, or "tell me about {ticker}".

---

## Task Overview

| Task | Name | Prerequisites | Output |
|------|------|--------------|--------|
| **1** | Data Ingestion | Ticker symbol | Raw filings + raw sections + DB |
| **2** | Company Research | `10k_raw_sections.json` | 6 structured JSON files |
| **3** | Financial Analysis | Tasks 1–2 | `comps_table.json` |
| **4** | Report Generation | Tasks 1–3 | `company_profile.md` + DB row |

**Default mode**: Run all 4 tasks sequentially. If the user requests a specific task, execute only that task.

---

## Task 1: Data Ingestion

**Purpose**: Fetch SEC filings, ingest XBRL financials to PostgreSQL, extract 10-K section text.

### Run the script:
```bash
uv run python skills/company-profile/scripts/ingest.py {TICKER}
# Optional flags:
#   --years 7        load 7 years of history (default: 5)
#   --quarterly      also load quarterly statements
```

The script does the following automatically:
1. **Resolve ticker → CIK** via SEC company_tickers.json
2. **Run XBRL ETL** (`ingest_company()`) → income statements, balance sheets, cash flows, derived metrics → PostgreSQL
3. **Download latest 10-K and 10-Q HTML** → `data/raw/{TICKER}/`
4. **Extract raw section text** from 10-K → `data/processed/{TICKER}/10k_raw_sections.json`:
   - `item1_business` — Item 1: Business description
   - `item1a_risk_factors` — Item 1A: Risk Factors
   - `item7_mda` — Item 7: MD&A
   - `item10_directors` — Item 10: Executive Officers

### Verify completeness:
```sql
SELECT fiscal_year, revenue/1e9 AS rev_b, gross_margin*100 AS gm_pct
FROM income_statements i
JOIN financial_metrics m USING (ticker, fiscal_year)
WHERE i.ticker = '{ticker}' AND i.fiscal_quarter IS NULL
ORDER BY fiscal_year;
```
Require **at least 3 years** of annual data before proceeding.

### Detect and record stock splits:
After ingestion, query yfinance for split history and save it for downstream use:
```python
import yfinance as yf, json
from pathlib import Path

splits = yf.Ticker(ticker).splits
if not splits.empty:
    split_data = {
        "ticker": ticker,
        "splits": [
            {"date": str(d.date()), "ratio": float(r)}
            for d, r in splits.items()
        ],
        "source": "yfinance"
    }
    out = Path(f"data/processed/{ticker}/stock_splits.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(split_data, indent=2))
```
This file is consumed by `generate_report.py` to split-adjust all per-share metrics.

**Task 1 Outputs**:
- `data/raw/{TICKER}/10-K_{date}.htm` — raw annual filing
- `data/raw/{TICKER}/10-Q_{date}.htm` — most recent quarterly filing
- `data/processed/{TICKER}/10k_raw_sections.json` — extracted section text
- PostgreSQL: `companies`, `income_statements`, `balance_sheets`, `cash_flow_statements`, `financial_metrics`, `sec_filings`

---

## Task 2: Company Research (AI-Driven)

**Purpose**: Read the raw 10-K sections and produce 6 structured JSON files. This task is entirely AI-driven — no script is needed. Read `data/processed/{TICKER}/10k_raw_sections.json` and create each file below.

### JSON files to create in `data/processed/{TICKER}/`:

#### `company_overview.json`
```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "cik": "0000320193",
  "fiscal_year": 2025,
  "fiscal_year_end": "September",
  "source": "10-K FY2025 Item 1",
  "description": "...",        // 2-3 sentence business description from Item 1
  "business_overview": "...",  // additional detail, 1-2 paragraphs
  "revenue_model": "...",      // how the company monetizes
  "customers": "...",          // key customer segments
  "segments": [
    {
      "name": "iPhone",
      "description": "...",
      "revenue_fy_b": 210.0,
      "yoy_growth_pct": 5.2
    }
  ],
  "products": ["...", "..."],
  "geographic_revenue": {
    "Americas": "~42%",
    "Europe": "~25%"
  }
}
```

#### `management_team.json`
```json
{
  "ticker": "AAPL",
  "source": "10-K FY2025 Item 10 + proxy DEF 14A",
  "executives": [
    {
      "name": "Tim Cook",
      "title": "Chief Executive Officer",
      "age": 64,
      "tenure_years": 14,
      "prior_roles": ["COO at Apple", "VP Operations at Compaq"],
      "accomplishments": "...",
      "insider_ownership_pct": "~0.02%"
    }
  ],
  "board": {
    "size": 8,
    "independent_directors": 7,
    "notable_members": ["..."]
  },
  "governance_notes": "..."
}
```

#### `risk_factors.json`
```json
{
  "ticker": "AAPL",
  "source": "10-K FY2025 Item 1A",
  "risks": [
    {
      "category": "Company-Specific",   // Company-Specific | Industry/Market | Financial | Macro
      "title": "Supply chain concentration",
      "description": "..."              // 1-2 sentences, verbatim or close paraphrase from 10-K
    }
  ]
}
```
Include **8–12 risks** across 4 categories: Company-Specific (4–6), Industry/Market (2–3), Financial (1–2), Macro (1–2).

#### `competitive_landscape.json`
```json
{
  "ticker": "AAPL",
  "source": "10-K FY2025 + market research",
  "moat": "...",
  "competitive_positioning": "...",
  "competitors": [
    {
      "name": "Samsung Electronics",
      "ticker": "005930.KS",
      "market_cap_b": 280,
      "products_competing": "...",
      "competitive_advantage_vs_subject": "...",
      "market_share": "..."
    }
  ]
}
```
Include **5–8 competitors** (direct + indirect). The `ticker` field is used by `build_comps.py` for peer data — use the primary exchange ticker (e.g. `SAMSG` → use `SSNLF` for OTC, or omit non-tradeable).

#### `financial_segments.json`
```json
{
  "ticker": "AAPL",
  "source": "10-K FY2025 MD&A",
  "fiscal_year": 2025,
  "segments": [
    { "name": "iPhone", "revenue_fy_b": 210.0, "revenue_prior_fy_b": 200.6, "yoy_growth_pct": 4.7, "description": "..." }
  ],
  "geographic_revenue_fy": {
    "Americas": { "revenue_b": 165.0, "pct": 42.0 }
  }
}
```

#### `investment_thesis.json`
```json
{
  "ticker": "AAPL",
  "source": "10-K FY2025 MD&A + analysis",
  "bull_case": [
    {
      "title": "Services revenue flywheel",
      "description": "..."     // 2-3 sentences with specific data points
    }
  ],
  "opportunities": [
    {
      "title": "Apple Intelligence / AI expansion",
      "description": "..."
    }
  ]
}
```
Include **4–6 bull case points** and **3–5 opportunities**, each with specific data or filing references.

### Step 2 guidelines:
- Source each fact to Item 1, Item 1A, or Item 7 of the 10-K
- For risk_factors.json: quote or closely paraphrase actual Item 1A language
- For competitive_landscape.json: use tickers that `build_comps.py` can look up on Yahoo Finance
- Cross-check revenue segment figures against the XBRL data in PostgreSQL

**Task 2 Outputs**: 6 JSON files in `data/processed/{TICKER}/`

---

## Task 3: Financial Analysis

**Purpose**: Build comparable company analysis table.

### Run the script:
```bash
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
# Optional: override peer list
uv run python skills/company-profile/scripts/build_comps.py {TICKER} --peers AMD,INTC,AVGO,QCOM
```

The script:
1. Reads peer tickers from `competitive_landscape.json` (preferred — uses the curated list from Task 2)
2. Falls back to yfinance peer discovery if the JSON is absent
3. Fetches market cap, revenue LTM, revenue growth, gross/op margins, P/E fwd, EV/EBITDA, P/S for each peer
4. Computes peer median / mean / min / max
5. Saves → `data/processed/{TICKER}/comps_table.json`

**Note on historical financials**: The 5-year financial table and returns analysis are computed directly from PostgreSQL by `generate_report.py` in Task 4. No separate step needed here.

**Task 3 Outputs**:
- `data/processed/{TICKER}/comps_table.json`

---

## Task 4: Report Generation

**Purpose**: Assemble all data into a comprehensive markdown report.

### Run the script:
```bash
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
# Optional: supply price if yfinance is stale
uv run python skills/company-profile/scripts/generate_report.py {TICKER} --price 225.50
```

The script reads all JSON files from `data/processed/{TICKER}/` and queries PostgreSQL to produce a report with these sections:

1. **Header** — ticker, price, market cap, sector, industry, date
2. **Business Summary** — from `company_overview.json` (10-K Item 1)
3. **Management Team** — from `management_team.json`
4. **Key Financial Metrics** — 5-year table from PostgreSQL
5. **Margin Analysis** — with YoY trend commentary
6. **Balance Sheet Snapshot** — latest vs prior year
7. **Returns & Efficiency** — ROE, ROA, ROIC
8. **Valuation** — P/E fwd/TTM, EV/EBITDA, P/S, P/B, FCF Yield
9. **Comparable Company Analysis** — from `comps_table.json`
10. **Competitive Landscape** — from `competitive_landscape.json`
11. **Investment Thesis** — from `investment_thesis.json`
12. **Key Risks** — from `risk_factors.json`
13. **Opportunities & Catalysts** — from `investment_thesis.json`
14. **Appendix** — data sources

**Formatting rules** applied by the script:
- Dollar amounts in billions (`$16.7B`) for revenue/assets; millions for smaller items
- Percentages to 1 decimal place
- Growth rates with directional arrow: `+25.3%↑` or `-4.1%↓`
- `N/A` for any missing data point
- **Per-share metrics are split-adjusted** using `data/processed/{TICKER}/stock_splits.json` — all historical EPS, DPS, and book value per share are restated to current share basis for apples-to-apples comparison across years

**Task 4 Outputs**:
- `data/reports/{TICKER}/company_profile.md`
- `analysis_reports` table row (PostgreSQL)
- View in Streamlit: `http://localhost:8501`

---

## Quality Checks

- [ ] `data/raw/{TICKER}/10-K_*.htm` exists (raw annual filing downloaded)
- [ ] `data/processed/{TICKER}/10k_raw_sections.json` exists with non-empty sections
- [ ] All 6 JSON files exist in `data/processed/{TICKER}/`
- [ ] At least 3 years of annual data in all DB tables
- [ ] Revenue figures in correct magnitude (billions vs millions — verify against XBRL)
- [ ] **Stock split adjustment**: If the company has had stock splits, verify `stock_splits.json` exists and all per-share metrics (EPS, DPS, shares outstanding) are adjusted to the current share basis. Compare adjusted EPS against yfinance's split-adjusted values as a sanity check (should match within 1%)
- [ ] Growth rates computed correctly: (current − prior) / prior
- [ ] Margins sanity check: gross 20–90%, operating −20% to +80%
- [ ] Management team: 3–5 executives with substantive bios (not placeholder text)
- [ ] Competitive landscape: 5–8 competitors with valid tickers for comps lookup
- [ ] `comps_table.json` has actual data (not all N/A)
- [ ] Risk factors sourced from Item 1A language
- [ ] `investment_thesis.json` has 4–6 bull case items with data points
- [ ] Report saved to both filesystem and database

---

## Scripts Reference

All scripts live in `skills/company-profile/scripts/` and are run from the **project root**:

```bash
# Full workflow for any ticker
uv run python skills/company-profile/scripts/ingest.py {TICKER}
# → Then complete Task 2 manually (create 6 JSON files)
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
```

| Script | Key args | Output files |
|--------|---------|-------------|
| `ingest.py TICKER` | `--years N`, `--quarterly` | `data/raw/TICKER/`, `data/processed/TICKER/10k_raw_sections.json`, PostgreSQL |
| `build_comps.py TICKER` | `--peers A,B,C` | `data/processed/TICKER/comps_table.json` |
| `generate_report.py TICKER` | `--price N.NN` | `data/reports/TICKER/company_profile.md`, `analysis_reports` DB row |

## Reference Files

- `references/tearsheet-template.md` — Report section template
- `references/data-sources.md` — Where each data point comes from
