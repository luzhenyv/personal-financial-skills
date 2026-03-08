---
name: company-profile
description: Generate a comprehensive company profile report for a US public company through a 4-task workflow — (1) data ingestion from SEC 10-K/Q filings, yfinance, and web search, (2) company research including management, competitive landscape, and risks, (3) financial analysis with comparable companies, (4) report generation. Raw filings saved to data/raw/{ticker}/, processed data to data/processed/{ticker}/, structured data to PostgreSQL.
---

# Company Profile

Generate a comprehensive company profile report through a structured 4-task workflow. Each task builds on prior outputs.

## Overview

This skill produces company profile reports sourced primarily from **SEC 10-K/Q filings** (the authoritative source), supplemented by yfinance and web search.

**Data Flow**: SEC EDGAR → `data/raw/{ticker}/` → `data/processed/{ticker}/*.json` → PostgreSQL → `data/reports/{ticker}/company_profile.md` → Streamlit (`http://localhost:8501`)

**Data Source Priority**: (1) SEC EDGAR XBRL+HTML, (2) yfinance, (3) Alpha Vantage (tiebreaker when sources conflict by >2%). See `references/data-sources.md` for full mapping.

**Stock Split Adjustment**: All per-share metrics must be split-adjusted to current share basis. See `references/stock-split-adjustment.md` for rules and implementation.

## Trigger

User asks for company overview, profile, tearsheet, or "tell me about {ticker}".

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

```bash
uv run python skills/company-profile/scripts/ingest.py {TICKER}
#   --years 5        load 5 years of history (default: 5)
#   --quarterly      also load quarterly statements
```

The script automatically: resolves ticker→CIK, runs XBRL ETL to PostgreSQL, downloads 10-K/Q HTML to `data/raw/{TICKER}/`, extracts section text to `data/processed/{TICKER}/10k_raw_sections.json` (items 1, 1A, 7, 10), and saves stock split history to `stock_splits.json`.

Require **at least 3 years** of annual data before proceeding.

**Outputs**: `data/raw/{TICKER}/10-K_*.htm`, `10k_raw_sections.json`, `stock_splits.json`, PostgreSQL tables (`companies`, `income_statements`, `balance_sheets`, `cash_flow_statements`, `financial_metrics`, `sec_filings`)

---

## Task 2: Company Research (AI-Driven)

Read `data/processed/{TICKER}/10k_raw_sections.json` and create 6 structured JSON files in `data/processed/{TICKER}/`. No script — this is entirely AI-driven.

**Files to create** (see `references/json-schemas.md` for full schemas):

| File | Source | Key content |
|------|--------|-------------|
| `company_overview.json` | Item 1 | Description, segments, revenue model, geographic split |
| `management_team.json` | Item 10 + DEF 14A | 3–5 executives with bios, board composition |
| `risk_factors.json` | Item 1A | 8–12 risks across 4 categories, quoting/paraphrasing filing |
| `competitive_landscape.json` | Item 1 + research | Moat, 5–8 competitors with tradeable tickers |
| `financial_segments.json` | MD&A | Segment revenue with YoY growth, geographic breakdown |
| `investment_thesis.json` | MD&A + analysis | 4–6 bull case points, 3–5 opportunities with data |

---

## Task 3: Financial Analysis

```bash
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
#   --peers AMD,INTC,AVGO,QCOM    override peer list
```

Reads peers from `competitive_landscape.json`, fetches market cap / revenue / margins / multiples via yfinance, computes peer statistics. Saves → `data/processed/{TICKER}/comps_table.json`.

---

## Task 4: Report Generation

```bash
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
#   --price 225.50    supply price if yfinance is stale
```

Assembles all JSON files + PostgreSQL data into a markdown report with 14 sections (header, business summary, management, financials, margins, balance sheet, returns, valuation, comps, competitive landscape, thesis, risks, opportunities, appendix). See `references/tearsheet-template.md` for the report template.

**Formatting**: billions for large amounts (`$16.7B`), 1 decimal % , directional arrows (`+25.3%↑`), `N/A` for missing data, split-adjusted per-share metrics.

**Outputs**: `data/reports/{TICKER}/company_profile.md`, `analysis_reports` DB row, viewable in Streamlit.

---

## Quick Reference

```bash
# Full workflow
uv run python skills/company-profile/scripts/ingest.py {TICKER}
# → Complete Task 2 manually (create 6 JSON files)
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
```

## Quality Checks

See `references/quality-checks.md` for the full checklist.

## Reference Files

- `references/tearsheet-template.md` — Report section template
- `references/data-sources.md` — Where each data point comes from
- `references/json-schemas.md` — Task 2 JSON file schemas with examples
- `references/stock-split-adjustment.md` — Split adjustment rules and code
- `references/quality-checks.md` — Post-run verification checklist
