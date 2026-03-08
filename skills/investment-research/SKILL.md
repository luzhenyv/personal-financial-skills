---
name: investment-research
description: Personal investor research workflow — 3-task pipeline that produces company deep-dive, valuation with scenarios, and an actionable investment report. Uses SEC EDGAR + PostgreSQL + yfinance. Viewable in Streamlit dashboard.
---

# Investment Research (Personal Workflow)

Structured research workflow for personal investors evaluating US public companies.
Produces an actionable investment report with DCF valuation, scenario analysis, and position sizing.

## Origin

Adapted from `equity-research/skills/initiating-coverage/` in [financial-services-plugins](https://github.com/anthropics/financial-services-plugins).

| Original (5-Task Institutional) | This Skill (3-Task Personal) |
|--------------------------------|------------------------------|
| 6-8K word research document | Focused tearsheet + business context |
| Excel model (6 tabs) | Python-based DCF & metrics |
| 25-35 PNG/JPG charts | Interactive Streamlit + Plotly |
| 30-50 page DOCX report | 5-8 page markdown + dashboard |
| Bloomberg / CapIQ / FactSet | SEC EDGAR + yfinance (free) |
| Analyst team workflow | Solo investor workflow |

## Data Architecture

```
SEC EDGAR XBRL ──→ PostgreSQL ──→ Python Analysis ──→ Streamlit Dashboard
     │                  │               │                    │
     ├─ 10-K filings    ├─ companies    ├─ company_profile   ├─ Company Profile
     ├─ Income Stmt     ├─ financials   ├─ valuation.py      ├─ Valuation & DCF
     ├─ Balance Sheet   ├─ metrics      ├─ investment_report  ├─ Investment Report
     └─ Cash Flow       └─ prices       └─ yfinance_client   └─ Download .md
```

## Prerequisites

- PostgreSQL running (via `docker compose up -d postgres`)
- Python environment with dependencies installed (`uv sync`)
- `.env` configured with `DATABASE_URL` and `SEC_USER_AGENT`

---

## Task 1: Company Deep Dive

**Purpose**: Ingest SEC data, build company profile, understand the business.

**Prerequisites**: Ticker symbol only

**Process**:

### Step 1.1 — Ingest Financial Data

```python
from src.etl.pipeline import ingest_company

result = ingest_company("NVDA", years=10, include_prices=True)
# Returns: {income_statements: N, balance_sheets: N, errors: [...]}
```

This pulls from SEC EDGAR XBRL:
- Income statements (annual)
- Balance sheets (annual)
- Cash flow statements (annual)
- Company metadata (SIC code, description, etc.)
- Computes financial metrics (margins, returns, ratios)

### Step 1.2 — Enrich with Market Data

```python
from src.etl.yfinance_client import get_stock_info, get_current_price

info = get_stock_info("NVDA")
# Returns: sector, industry, market_cap, current_price, beta, description, etc.

price = get_current_price("NVDA")
```

### Step 1.3 — Generate Tearsheet

```python
from src.analysis.company_profile import generate_tearsheet

tearsheet_md = generate_tearsheet("NVDA")
# Saves to data/reports/NVDA/tearsheet.md + database
```

### Step 1.4 — Review in Streamlit

Open the **Company Profile** page to review:
- Revenue & income trends (bar charts)
- Margin analysis (line charts)
- Balance sheet composition
- Cash flow waterfall
- Key metrics table

```bash
streamlit run streamlit_app/app.py
```

**Output**: Tearsheet (.md) + interactive dashboard
**Verify**: Revenue figures match SEC filings, margins look reasonable

---

## Task 2: Valuation & Scenarios

**Purpose**: Build DCF model, run scenario analysis, compare with peers.

**Prerequisites**: Task 1 completed (financial data in PostgreSQL)

**Process**:

### Step 2.1 — DCF Valuation

```python
from src.analysis.valuation import simple_dcf

dcf = simple_dcf(
    "NVDA",
    revenue_growth=0.15,        # Base case revenue growth
    revenue_growth_decay=0.01,  # Growth decelerates each year
    wacc=0.10,                  # Discount rate
    terminal_growth=0.03,       # Perpetuity growth
    projection_years=5,
)
# Returns: DCFResult with implied_price, projected_fcf, sensitivity grid
```

**Key parameters to adjust**:

| Parameter | Conservative | Base | Aggressive |
|-----------|-------------|------|------------|
| Revenue Growth | 5-8% | 10-15% | 20-30% |
| WACC | 12-14% | 9-11% | 7-8% |
| Terminal Growth | 2.0% | 2.5-3.0% | 3.5% |
| Operating Margin | Historical avg | Slight expansion | Best-in-class |

### Step 2.2 — Scenario Analysis

```python
from src.analysis.valuation import scenario_analysis

scenarios = scenario_analysis(
    "NVDA",
    bull_growth=0.25,   # AI boom continues
    base_growth=0.12,   # Steady growth
    bear_growth=0.03,   # Cyclical downturn
    wacc=0.10,
)
# Returns: ScenarioResult with bull/base/bear implied prices
```

### Step 2.3 — Peer Comparison

```python
from src.analysis.valuation import peer_comps

comps = peer_comps("NVDA")
# Returns: CompsResult with peer multiples and implied valuations
```

### Step 2.4 — Combined Summary

```python
from src.analysis.valuation import valuation_summary

val = valuation_summary("NVDA", revenue_growth=0.12, wacc=0.10)
# Returns: ValuationSummary with recommendation (BUY/HOLD/SELL),
#          weighted target price, all sub-analyses
```

### Step 2.5 — Interactive Exploration in Streamlit

Open the **Valuation** page for:
- DCF parameter sliders (adjust growth, WACC, margin in real-time)
- Sensitivity heatmap (price vs WACC × terminal growth)
- Scenario comparison (bull/base/bear bar chart)
- Peer comparison table
- Price target waterfall

**Output**: Valuation results in memory + Streamlit visualization
**Verify**: Implied price makes directional sense vs current market

---

## Task 3: Investment Report

**Purpose**: Generate a comprehensive, actionable investment report.

**Prerequisites**: Tasks 1 and 2 completed

**Process**:

### Step 3.1 — Generate Report

```python
from src.analysis.investment_report import generate_investment_report

report_md = generate_investment_report(
    "NVDA",
    revenue_growth=0.12,
    wacc=0.10,
    save=True,  # Saves to file + database
)
```

### Step 3.2 — Report Sections

The generated report includes:

1. **Header** — Price, target, rating, market cap
2. **Investment Rating** — BUY/HOLD/SELL with method breakdown
3. **Company Overview** — Business description, sector, SIC
4. **Financial Performance** — Revenue, income, EPS, margin trends (table)
5. **Balance Sheet** — Cash, debt, equity, ratios
6. **Cash Flow** — Operations, CapEx, FCF, SBC
7. **Valuation Analysis** — DCF model + sensitivity table + peer comps
8. **Scenario Analysis** — Bull/Base/Bear comparison table
9. **Investment Thesis & Risks** — Data-driven bull/bear cases
10. **Action Plan** — Position sizing guide at various investment amounts

### Step 3.3 — Review & Download via Streamlit

The **Investment Report** tab on the Company Profile page shows:
- Full rendered report
- Download button for .md file
- Key metrics summary cards

**Output**: `data/reports/{ticker}/investment_report.md` + database record
**Verify**: Recommendation aligns with your analysis, position sizing is reasonable

---

## Quick Start Example (NVDA)

```bash
# 1. Start PostgreSQL
docker compose up -d postgres

# 2. Ingest NVDA data
python -c "
from src.etl.pipeline import ingest_company
result = ingest_company('NVDA', years=10, include_prices=True)
print(f'Loaded {result[\"income_statements\"]} years of data')
"

# 3. Generate investment report
python -c "
from src.analysis.investment_report import generate_investment_report
report = generate_investment_report('NVDA', revenue_growth=0.12, wacc=0.10)
print(f'Report generated: {len(report)} chars')
"

# 4. Launch dashboard
streamlit run streamlit_app/app.py
```

---

## Python Modules

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `src/etl/pipeline.py` | SEC EDGAR data ingestion | `ingest_company()` |
| `src/etl/sec_client.py` | SEC API client | `get_company_filings()`, `get_xbrl_data()` |
| `src/etl/xbrl_parser.py` | XBRL tag mapping | `parse_income_statement()`, `compute_metrics()` |
| `src/etl/yfinance_client.py` | Market data supplement | `get_stock_info()`, `get_current_price()`, `get_peers()` |
| `src/analysis/company_profile.py` | Tearsheet generation | `generate_tearsheet()`, `get_profile_data()` |
| `src/analysis/valuation.py` | DCF, comps, scenarios | `simple_dcf()`, `peer_comps()`, `scenario_analysis()` |
| `src/analysis/investment_report.py` | Full report generator | `generate_investment_report()` |

## Streamlit Pages

| Page | Purpose |
|------|---------|
| **Home** | Dashboard overview |
| **Company Profile** | Tearsheet, financials, charts, investment report |
| **Valuation** | Interactive DCF, sensitivity, scenarios |

## Quality Checks

- [ ] At least 3 years of financial data loaded
- [ ] Revenue figures match SEC EDGAR 10-K filings
- [ ] DCF implied price is directionally reasonable
- [ ] Sensitivity range covers realistic WACC/growth scenarios
- [ ] Report includes all 10 sections
- [ ] Bull/Base/Bear scenarios span meaningful range
- [ ] Position sizing reflects your actual portfolio budget

## Limitations vs Institutional Workflow

| Limitation | Why | Workaround |
|-----------|-----|------------|
| Annual data only | SEC XBRL quarterly parsing is complex | Will add quarterly in v2 |
| No real-time quotes | Uses delayed yfinance data | Check broker for live prices |
| Limited peer data | Only companies you've ingested | Ingest 3-5 peers manually |
| No chart export | Charts are in-browser Plotly | Screenshot or use Plotly export |
| No Word/PDF output | Markdown only | Use pandoc to convert if needed |
