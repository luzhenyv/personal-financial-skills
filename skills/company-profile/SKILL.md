---
name: company-profile
description: Generate a comprehensive company profile report for a US public company through a 4-task workflow — (1) data ingestion from SEC 10-K/Q filings, yfinance, and web search, (2) company research including management, competitive landscape, and risks, (3) financial analysis with comparable companies, (4) report generation. Raw filings saved to data/raw/{ticker}/, processed data to data/processed/{ticker}/, structured data to PostgreSQL.
---

# Company Profile

Generate a comprehensive company profile report through a structured 4-task workflow. Each task builds on prior outputs.

## Overview

This skill produces company profile reports sourced primarily from **SEC 10-K/Q filings** (the authoritative source), supplemented by yfinance, Alpha Vantage, and web search. Unlike a simple tearsheet, the output includes management team analysis, competitive landscape, comparable company analysis, and risks/opportunities extracted from actual filings.

**Data Flow**:
```
SEC EDGAR (10-K/Q PDF) → data/raw/{ticker}/
LLM-parsed + cross-referenced → data/processed/{ticker}/
Structured financials → PostgreSQL
Report → data/reports/{ticker}/company_profile.md + analysis_reports table
Interactive view → Streamlit app
```

---

## Trigger

User asks for company overview, profile, tearsheet, or "tell me about {ticker}".

---

## Task Overview

| Task | Name | Prerequisites | Output |
|------|------|--------------|--------|
| **1** | Data Ingestion | Ticker symbol | Raw filings + structured DB data |
| **2** | Company Research | Task 1 data | Management, competitive landscape, risks/opportunities |
| **3** | Financial Analysis | Tasks 1-2 | Metrics, margins, comparable companies |
| **4** | Report Generation | Tasks 1-3 | Markdown profile + DB upsert |

**Default mode**: Run all 4 tasks sequentially in a single invocation. If the user requests a specific task, execute only that task.

---

## Task 1: Data Ingestion

**Purpose**: Fetch SEC filings and market data; load structured financials into PostgreSQL.

### Step 1.1: Resolve Ticker → CIK
```python
from src.etl.pipeline import ingest_company
from src.etl import sec_client

cik = sec_client.ticker_to_cik("{ticker}")
```

### Step 1.2: Download 10-K/Q Filings
Fetch the latest 10-K (annual) and most recent 10-Q from SEC EDGAR.

- Get filing index via `sec_client.get_recent_filings(cik, filing_types=['10-K', '10-Q'])`
- Download the primary document PDF for each filing
- **Save PDFs to `data/raw/{ticker}/`** (e.g. `10-K_2025.pdf`, `10-Q_Q3_2025.pdf`)
- User will review these raw files

### Step 1.3: Parse Filings with LLM
Read the 10-K/Q PDFs and extract:
- Business description (Item 1)
- Risk factors (Item 1A)
- MD&A discussion (Item 7)
- Executive officers (Item 10 / proxy)
- Revenue segments, geographic breakdown
- Key metrics, guidance, outlook

Save LLM-parsed structured output as JSON to **`data/processed/{ticker}/`**:
- `company_overview.json` — business description, history, products
- `management_team.json` — executives with bios, tenure, compensation
- `risk_factors.json` — categorized risks from Item 1A
- `competitive_landscape.json` — competitors mentioned in filings + agent research
- `financial_segments.json` — revenue by segment/geography from filings

### Step 1.4: Cross-Reference with Market Data
Supplement filing data with yfinance and Alpha Vantage:
```python
from src.etl.yfinance_client import get_stock_info, get_peers, get_current_price
info = get_stock_info("{ticker}")
peers = get_peers("{ticker}")
```
Use market data to validate and enrich LLM-parsed figures (e.g., check revenue/EPS match between filing parse and yfinance).

### Step 1.5: Ingest Structured Data to PostgreSQL
```python
result = ingest_company("{ticker}")
```
This runs the full ETL pipeline: XBRL facts → income statements, balance sheets, cash flows, derived metrics, price data → PostgreSQL.

### Step 1.6: Verify Data Completeness
```sql
SELECT COUNT(*) FROM income_statements WHERE ticker = '{ticker}';
SELECT COUNT(*) FROM balance_sheets WHERE ticker = '{ticker}';
SELECT COUNT(*) FROM cash_flow_statements WHERE ticker = '{ticker}';
```
Require at least 3 years of annual data before proceeding.

**Task 1 Outputs**:
- `data/raw/{ticker}/` — 10-K/Q PDFs and XBRL JSON
- `data/processed/{ticker}/` — LLM-parsed JSON files
- PostgreSQL tables populated

---

## Task 2: Company Research

**Purpose**: Build qualitative understanding — management, competition, risks, opportunities — primarily from 10-K/Q content.

**Prerequisites**: Task 1 complete (parsed filings in `data/processed/{ticker}/`)

### Step 2.1: Management Team
From 10-K Item 10, proxy (DEF 14A), and web search:

For **3-5 key executives** (CEO, CFO, + 1-3 others):
- Name, title, age, tenure at company
- Prior roles (last 2-3 positions)
- Key accomplishments and track record
- Compensation summary (from proxy if available)
- Insider ownership percentage

Also note:
- Board composition and independence
- Recent management changes
- Governance quality assessment

### Step 2.2: Products & Business Model
From 10-K Item 1 and MD&A:
- Product/service portfolio with descriptions
- Revenue model (subscription, transaction, license, etc.)
- Customer segments (enterprise, SMB, consumer, government)
- Geographic distribution of revenue
- Key partnerships and distribution channels

### Step 2.3: Competitive Landscape
From 10-K mentions, web search, and agent knowledge:

Identify **5-8 competitors** (direct + indirect). For each:
- Company name, ticker (if public), market cap
- Key products competing in same space
- Estimated market share (if available)
- Competitive advantage vs. subject company

Create a competitive positioning summary:
- Company's moat / competitive advantages
- Competitive vulnerabilities
- Switching costs and network effects
- Market concentration (fragmented vs. consolidated)

### Step 2.4: TAM & Industry
From 10-K, industry reports, web search:
- Total Addressable Market (TAM) size and growth rate
- Industry growth drivers and headwinds
- Regulatory environment
- Technology trends affecting the industry

### Step 2.5: Risks & Opportunities
**From 10-K Item 1A (Risk Factors)** — extract and categorize:

**Risks** (8-12 items across 4 categories):
- Company-Specific (4-6): execution, concentration, key person, technology
- Industry/Market (2-3): competition, regulation, disruption
- Financial (1-2): debt, liquidity, profitability
- Macro (1-2): economic cycle, FX, geopolitical

**Opportunities** (3-5 items):
- New markets or products mentioned in MD&A
- Secular tailwinds
- Margin expansion drivers
- M&A or strategic initiatives

Each risk/opportunity: 1-2 sentences sourced from the actual filing.

**Task 2 Outputs**:
- Updated JSON files in `data/processed/{ticker}/`
- Qualitative research ready for report assembly

---

## Task 3: Financial Analysis

**Purpose**: Quantitative analysis — historical financials, margins, returns, and comparable company analysis.

**Prerequisites**: Task 1 complete (PostgreSQL data), Task 2 complete (peer list)

### Step 3.1: Query Historical Financials
```sql
SELECT * FROM income_statements
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;

SELECT * FROM balance_sheets
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;

SELECT * FROM cash_flow_statements
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;

SELECT * FROM financial_metrics
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;
```

### Step 3.2: Compute Key Metrics Table
5-year history of:
- Revenue, Revenue Growth
- Gross Profit, Operating Income, Net Income, EPS (Diluted)
- Free Cash Flow
- Margins: Gross, Operating, Net, FCF
- Returns: ROE, ROA, ROIC
- Leverage: Current Ratio, Debt/Equity

### Step 3.3: Latest Price & Valuation
```python
from src.etl.yfinance_client import get_current_price, get_stock_info
price = get_current_price("{ticker}")
info = get_stock_info("{ticker}")
```
Compute: P/E, P/S, P/B, EV/EBITDA, FCF Yield.

### Step 3.4: Comparable Company Analysis
Using peers from Task 2 (5-8 companies), build a comps table:

| Metric | {ticker} | Peer 1 | Peer 2 | ... | Median |
|--------|----------|--------|--------|-----|--------|
| Market Cap | | | | | |
| Revenue (LTM) | | | | | |
| Revenue Growth | | | | | |
| Gross Margin | | | | | |
| Operating Margin | | | | | |
| P/E | | | | | |
| EV/EBITDA | | | | | |
| P/S | | | | | |

For each peer, fetch data via yfinance: `get_stock_info(peer_ticker)`.

Include statistical summary row: Median, Mean, Min, Max.

Highlight where subject company trades at premium/discount to peer median.

**Task 3 Outputs**:
- Financial metrics computed and validated
- Comparable company analysis table
- Valuation context

---

## Task 4: Report Generation

**Purpose**: Assemble all data into a comprehensive markdown report and save.

**Prerequisites**: Tasks 1-3 complete

### Step 4.1: Build Report
Use the template in `references/tearsheet-template.md`. Fill all sections:

1. **Header** — ticker, sector, industry, price, market cap, date
2. **Business Summary** — from 10-K Item 1 (LLM-parsed), not generic
3. **Management Team** — 3-5 executives with bios from Task 2
4. **Key Financial Metrics** — 5-year table from Task 3
5. **Margin Analysis** — with trends
6. **Balance Sheet Snapshot** — latest year
7. **Returns & Efficiency** — ROE, ROA, ROIC
8. **Valuation** — current multiples
9. **Comparable Company Analysis** — peer comps table from Task 3
10. **Competitive Landscape** — positioning and moat from Task 2
11. **Investment Thesis** — bull case bullets (from filing analysis)
12. **Key Risks** — from 10-K Item 1A (Task 2)
13. **Opportunities & Catalysts** — from MD&A (Task 2)

### Step 4.2: Formatting Rules
- Dollar amounts in billions (÷ 1e9) for revenue/assets, millions for smaller items
- Percentages to 1 decimal place
- Growth rates with arrow: `+25.3%↑` or `-4.1%↓`
- Use `N/A` for missing data, never leave blank
- All data points attributable to source (10-K, yfinance, etc.)

### Step 4.3: Save Report
1. Write markdown to `data/reports/{ticker}/company_profile.md`
2. Upsert to `analysis_reports` table:
```sql
INSERT INTO analysis_reports (ticker, report_type, title, content_md, generated_by, file_path)
VALUES ('{ticker}', 'company_profile', '{name} Company Profile', '{content}', 'claude', '{path}')
ON CONFLICT (ticker, report_type) DO UPDATE SET content_md = EXCLUDED.content_md;
```

**Task 4 Outputs**:
- `data/reports/{ticker}/company_profile.md`
- `analysis_reports` table row
- User can view interactive version via Streamlit app at `http://localhost:8501`

---

## Quality Checks

- [ ] 10-K/Q PDFs saved to `data/raw/{ticker}/`
- [ ] Parsed JSONs saved to `data/processed/{ticker}/`
- [ ] At least 3 years of annual financial data in all tables
- [ ] Revenue figures in correct magnitude (billions vs millions)
- [ ] Growth rates match: (current - prior) / prior
- [ ] Margins between -100% and +100% (sanity check)
- [ ] Management team has 3-5 executives with substantive bios
- [ ] Competitive landscape has 5-8 named competitors
- [ ] Comparable company table has peer data (not all N/A)
- [ ] Risks sourced from actual 10-K Item 1A language
- [ ] File saved to both filesystem and database

## Reference Files

- `references/tearsheet-template.md` — Markdown template to fill
- `references/data-sources.md` — Where each data point comes from
