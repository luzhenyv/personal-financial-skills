---
name: company-profile
description: Generate a comprehensive company profile report for a US public company through a 3-task workflow — (1) company research from REST API data and SEC filings, (2) financial analysis with comparable companies, (3) report generation. ETL must be run separately before using this skill. All artifacts are written to data/artifacts/{ticker}/profile/.
---

# Company Profile

Generate a comprehensive company profile report through a structured 3-task workflow. Each task builds on prior outputs.

## Overview

This skill produces company profile reports by reading structured data from the **REST API** (backed by the database), supplemented by local SEC filings and market data providers. The agent **never writes to the database directly** — it reads through the REST API and writes artifacts to the filesystem.

**Data Flow**: `REST API / data/raw/{ticker}/ → Agent → data/artifacts/{ticker}/profile/*.json` → `data/artifacts/{ticker}/profile/company_profile.md` → Streamlit (`http://localhost:8501`)

**Data Source Priority** (fallback chain):
1. **REST API** (database) — most trustworthy, already validated by ETL
2. **Local SEC filings** (`data/raw/{ticker}/`) — raw 10-K/Q HTML for section text
3. **Alpha Vantage** — conflict resolution, alternative data
4. **yfinance** — supplemental price / basic fundamental data
5. **Web search** — last resort for news and qualitative context

See `references/data-sources.md` for full field-level mapping.

**Stock Split Adjustment**: All per-share metrics must be split-adjusted to current share basis. The REST API endpoint `GET /api/financials/{TICKER}/annual` handles this automatically; the agent can also call `GET /api/financials/{TICKER}/stock-splits` to inspect the split history.

## Trigger

User asks for company overview, profile, tearsheet, or "tell me about {ticker}".

## Prerequisite: ETL Ingestion

**This skill does NOT run data ingestion.** ETL is handled by the Data Plane (Plane 1) — a separate process. Before using this skill, verify that the company has been ingested:

1. Call `GET /api/companies/` — confirm the ticker appears
2. Call `GET /api/financials/{TICKER}/income-statements?years=3` — confirm at least 3 years of data
3. Verify `data/raw/{TICKER}/10-K_*.htm` exists (needed for Task 1 section extraction)

If the ticker is **not** in the database, instruct the user to run ETL first:
```bash
uv run python -m pfs.etl.pipeline ingest {TICKER} --years 5
```

## Task Overview

| Task | Name | Prerequisites | Output |
|------|------|--------------|--------|
| **1** | Company Research | REST API data + `data/raw/{TICKER}/` 10-K HTML | 6 structured JSON files in `profile/` |
| **2** | Financial Analysis | Task 1 `competitive_landscape.json` | `comps_table.json` in `profile/` |
| **3** | Report Generation | Tasks 1–2 + REST API data | `company_profile.md` in `profile/` |

**Default mode**: Run all 3 tasks sequentially. If the user requests a specific task, execute only that task.

---

## Task 1: Company Research

### Pre-step: Run deterministic extraction

```bash
uv run python skills/company-profile/scripts/extract_10k.py {TICKER}
```

This script reads `10k_raw_sections.json` and the REST API to produce `*_skeleton.json` files that pre-populate structured fields (executives, risk factor headings, segments, company metadata). The AI then enriches these skeletons with narrative analysis to produce the final 6 JSON files.

### AI-driven enrichment

Read data from the REST API, the skeleton files, and `data/artifacts/{TICKER}/profile/10k_raw_sections.json`. Create 6 structured JSON files in `data/artifacts/{TICKER}/profile/`.

**REST API endpoints to use**:
- `GET /api/companies/{TICKER}` — metadata, sector, description
- `GET /api/financials/{TICKER}/income-statements?years=5` — revenue, margins, EPS
- `GET /api/financials/{TICKER}/balance-sheets?years=5` — assets, liabilities
- `GET /api/financials/{TICKER}/cash-flows?years=5` — FCF, CapEx
- `GET /api/financials/{TICKER}/metrics` — computed ratios
- `GET /api/financials/{TICKER}/segments` — segment breakdown
- `GET /api/financials/{TICKER}/stock-splits` — split history for per-share adjustment
- `GET /api/filings/{TICKER}/?form_type=10-K` — filing history
- `GET /api/filings/{TICKER}/{ID}/content` — raw 10-K HTML (if `10k_raw_sections.json` is missing)

**Files to create** in `data/artifacts/{TICKER}/profile/` (see `references/json-schemas.md` for full schemas):

| File | Source | Key content |
|------|--------|-------------|
| `company_overview.json` | REST API + Item 1 | Description, segments, revenue model, geographic split |
| `management_team.json` | Item 10 + DEF 14A + web search | 3–5 executives with bios, board composition |
| `risk_factors.json` | Item 1A | 8–12 risks across 4 categories, quoting/paraphrasing filing |
| `competitive_landscape.json` | Item 1 + REST API + web search | Moat, 5–8 competitors with tradeable tickers |
| `financial_segments.json` | REST API segments + MD&A | Segment revenue with YoY growth, geographic breakdown |
| `investment_thesis.json` | REST API + MD&A + analysis | 4–6 bull case points, 3–5 opportunities with data |

---

## Task 2: Financial Analysis

```bash
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
#   --peers AMD,INTC,AVGO,QCOM    override peer list
#   --refresh                      bypass cache
```

Calls `GET /api/analysis/comps/{ticker}` to fetch peer comparison data. The server reads peers from `competitive_landscape.json`, fetches market data via yfinance with caching, and computes peer statistics. Saves → `data/artifacts/{TICKER}/profile/comps_table.json`.

---

## Task 3: Report Generation

### Pre-step (agent-driven): Write `financial_data.json` and `valuation_summary.json`

Before running the script, the agent must:
1. Call `GET /api/financials/{TICKER}/annual` → write to `data/artifacts/{TICKER}/profile/financial_data.json`
2. Call `GET /api/analysis/valuation/{TICKER}` → write to `data/artifacts/{TICKER}/profile/valuation_summary.json`

These files contain combined financials with split-adjusted EPS, and DCF valuation with bear/base/bull scenarios.

### Run the script

```bash
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
#   --price 225.50    supply price if yfinance is stale
```

Assembles all JSON files from `data/artifacts/{TICKER}/profile/` into a markdown report with 15 sections (header, business summary, management, financials, margins, balance sheet, returns, DCF valuation, valuation multiples, comps, competitive landscape, thesis, risks, opportunities, appendix).

**Formatting**: billions for large amounts (`$16.7B`), 1 decimal % , directional arrows (`+25.3%↑`), `N/A` for missing data, split-adjusted per-share metrics.

**Outputs**: `data/artifacts/{TICKER}/profile/company_profile.md`, viewable in Streamlit. Reports are version-controlled via git.

---

## Quick Reference

```bash
# Prerequisite: ensure ETL has ingested the ticker
uv run python -m pfs.etl.pipeline ingest {TICKER} --years 5

# Skill workflow
# → Task 1 pre-step: Deterministic extraction from 10-K
uv run python skills/company-profile/scripts/extract_10k.py {TICKER}
# → Task 1: AI enriches skeleton files into 6 JSON artifacts
# → Task 2: Comps via API
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
# → Task 3 pre-step: Agent writes financial_data.json + valuation_summary.json from API
uv run python skills/company-profile/scripts/generate_report.py {TICKER}
```

## Quality Checks

See `references/quality-checks.md` for the full checklist.

## Reference Files

- `references/data-sources.md` — Where each data point comes from
- `references/json-schemas.md` — Task 1 JSON file schemas with examples
- `references/quality-checks.md` — Post-run verification checklist
