---
name: company-profile
description: Generate a comprehensive company profile report for a US public company through a 3-task workflow — (1) company research from MCP data and SEC filings, (2) financial analysis with comparable companies, (3) report generation. ETL must be run separately before using this skill. All artifacts are written to data/artifacts/{ticker}/profile/.
---

# Company Profile

Generate a comprehensive company profile report through a structured 3-task workflow. Each task builds on prior outputs.

## Overview

This skill produces company profile reports by reading structured data from the **personal-finance MCP server** (PostgreSQL), supplemented by local SEC filings and market data providers. The agent **never writes to PostgreSQL** — it only reads through MCP tools and writes artifacts to the filesystem.

**Data Flow**: `MCP tools / data/raw/{ticker}/ → Agent → data/artifacts/{ticker}/profile/*.json` → `data/artifacts/{ticker}/profile/company_profile.md` → Streamlit (`http://localhost:8501`)

**Data Source Priority** (fallback chain):
1. **MCP** (PostgreSQL) — most trustworthy, already validated by ETL
2. **Local SEC filings** (`data/raw/{ticker}/`) — raw 10-K/Q HTML for section text
3. **Alpha Vantage** — conflict resolution, alternative data
4. **yfinance** — supplemental price / basic fundamental data
5. **Web search** — last resort for news and qualitative context

See `references/data-sources.md` for full field-level mapping.

**Stock Split Adjustment**: All per-share metrics must be split-adjusted to current share basis. The MCP tool `get_annual_financials` handles this automatically; the agent can also call `get_stock_splits` to inspect the split history.

## Trigger

User asks for company overview, profile, tearsheet, or "tell me about {ticker}".

## Prerequisite: ETL Ingestion

**This skill does NOT run data ingestion.** ETL is handled by the Data Plane (Plane 1) — a separate process. Before using this skill, verify that the company has been ingested:

1. Call MCP tool `list_companies` — confirm the ticker appears
2. Call MCP tool `get_income_statements(ticker, years=3)` — confirm at least 3 years of data
3. Verify `data/raw/{TICKER}/10-K_*.htm` exists (needed for Task 1 section extraction)

If the ticker is **not** in the database, instruct the user to run ETL first:
```bash
uv run python -m src.etl.pipeline ingest {TICKER} --years 5
```

## Task Overview

| Task | Name | Prerequisites | Output |
|------|------|--------------|--------|
| **1** | Company Research | MCP data + `data/raw/{TICKER}/` 10-K HTML | 6 structured JSON files in `profile/` |
| **2** | Financial Analysis | Task 1 `competitive_landscape.json` | `comps_table.json` in `profile/` |
| **3** | Report Generation | Tasks 1–2 + MCP data | `company_profile.md` in `profile/` + DB row |

**Default mode**: Run all 3 tasks sequentially. If the user requests a specific task, execute only that task.

---

## Task 1: Company Research (AI-Driven)

Read data from MCP tools and `data/artifacts/{TICKER}/profile/10k_raw_sections.json` (extracted by the ETL pipeline). Create 6 structured JSON files in `data/artifacts/{TICKER}/profile/`. No script — this is entirely AI-driven.

**MCP tools to use**:
- `get_company(ticker)` — metadata, sector, description
- `get_income_statements(ticker, years=5)` — revenue, margins, EPS
- `get_balance_sheets(ticker, years=5)` — assets, liabilities
- `get_cash_flows(ticker, years=5)` — FCF, CapEx
- `get_financial_metrics(ticker)` — computed ratios
- `get_revenue_segments(ticker)` — segment breakdown
- `get_stock_splits(ticker)` — split history for per-share adjustment
- `list_filings(ticker, form_type="10-K")` — filing history
- `get_filing_content(ticker, filing_id)` — raw 10-K HTML (if `10k_raw_sections.json` is missing)

**Files to create** in `data/artifacts/{TICKER}/profile/` (see `references/json-schemas.md` for full schemas):

| File | Source | Key content |
|------|--------|-------------|
| `company_overview.json` | MCP + Item 1 | Description, segments, revenue model, geographic split |
| `management_team.json` | Item 10 + DEF 14A + web search | 3–5 executives with bios, board composition |
| `risk_factors.json` | Item 1A | 8–12 risks across 4 categories, quoting/paraphrasing filing |
| `competitive_landscape.json` | Item 1 + MCP + web search | Moat, 5–8 competitors with tradeable tickers |
| `financial_segments.json` | MCP segments + MD&A | Segment revenue with YoY growth, geographic breakdown |
| `investment_thesis.json` | MCP + MD&A + analysis | 4–6 bull case points, 3–5 opportunities with data |

---

## Task 2: Financial Analysis

```bash
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
#   --peers AMD,INTC,AVGO,QCOM    override peer list
```

Reads peers from `data/artifacts/{TICKER}/profile/competitive_landscape.json`, fetches market cap / revenue / margins / multiples via yfinance, computes peer statistics. Saves → `data/artifacts/{TICKER}/profile/comps_table.json`.

---

## Task 3: Report Generation

### Pre-step (agent-driven): Write `financial_data.json`

Before running the script, the agent must call MCP `get_annual_financials(ticker)` and write the result to `data/artifacts/{TICKER}/profile/financial_data.json`. This file contains combined income, balance sheet, cash flow, and metric data with split-adjusted EPS.

### Run the script

```bash
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
#   --price 225.50    supply price if yfinance is stale
```

Assembles all JSON files from `data/artifacts/{TICKER}/profile/` into a markdown report with 14 sections (header, business summary, management, financials, margins, balance sheet, returns, valuation, comps, competitive landscape, thesis, risks, opportunities, appendix).

**Formatting**: billions for large amounts (`$16.7B`), 1 decimal % , directional arrows (`+25.3%↑`), `N/A` for missing data, split-adjusted per-share metrics.

### Post-step (agent-driven): Persist to DB

After the script runs, call MCP `save_analysis_report(ticker, 'company_profile', title, content_md, file_path)` to upsert the report into the `analysis_reports` table. Read the generated `company_profile.md` and pass its content.

**Outputs**: `data/artifacts/{TICKER}/profile/company_profile.md`, viewable in Streamlit.

---

## Quick Reference

```bash
# Prerequisite: ensure ETL has ingested the ticker
uv run python -m src.etl.pipeline ingest {TICKER} --years 5

# Skill workflow
# → Task 1: Create 6 JSON files via AI using MCP data
# → Task 2:
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
# → Task 3 pre-step: Agent calls MCP get_annual_financials → writes financial_data.json
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
# → Task 3 post-step: Agent calls MCP save_analysis_report to persist in DB
```

## Quality Checks

See `references/quality-checks.md` for the full checklist.

## Reference Files

- `references/data-sources.md` — Where each data point comes from
- `references/json-schemas.md` — Task 1 JSON file schemas with examples
- `references/quality-checks.md` — Post-run verification checklist
