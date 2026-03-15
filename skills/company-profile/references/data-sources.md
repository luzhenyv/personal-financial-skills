# Data Sources Reference

Maps each data field in the company profile to its source and storage location.

## Data Source Priority (Fallback Chain)

```
1. MCP (PostgreSQL)     ← most trustworthy, already validated by ETL
2. Local SEC files      ← data/raw/{ticker}/ 10-K/Q HTML for section text
3. Alpha Vantage        ← conflict resolution, alternative data
4. yfinance             ← supplemental price / basic fundamental data
5. Web search           ← last resort for news, qualitative context
```

## Data Flow

```
MCP tools (PostgreSQL) → Agent reads structured data
data/raw/{ticker}/ → Agent reads raw 10-K/Q HTML for section text
Agent → data/artifacts/{ticker}/profile/ (structured JSON + report)
```

## Company Metadata

| Field | Primary Source | Fallback | Storage |
|-------|---------------|----------|---------|
| Company Name | SEC Submissions API | yfinance | `companies.name` |
| Ticker | SEC Company Tickers | — | `companies.ticker` |
| CIK | SEC Company Tickers | — | `companies.cik` |
| Sector / Industry | yfinance | SEC SIC Code → mapping | `companies.sector`, `companies.industry` |
| Exchange | SEC Submissions API | yfinance | `companies.exchange` |
| Fiscal Year End | SEC Submissions API | — | `companies.fiscal_year_end` |
| Description | 10-K Item 1 (LLM-parsed) | yfinance `longBusinessSummary` | `companies.description` |
| Website | SEC Submissions API | yfinance | `companies.website` |
| Market Cap | yfinance | Calculated: Price × Shares | `companies.market_cap` |
| Employee Count | yfinance | 10-K Item 1 | `artifacts/{ticker}/profile/company_overview.json` |

## Management Team (NEW)

| Field | Primary Source | Fallback | Storage |
|-------|---------------|----------|---------|
| Executive Names/Titles | 10-K Item 10 | DEF 14A Proxy | `artifacts/{ticker}/profile/management_team.json` |
| Bios & Background | DEF 14A + Web Search | LinkedIn, press | `artifacts/{ticker}/profile/management_team.json` |
| Compensation | DEF 14A Proxy | — | `artifacts/{ticker}/profile/management_team.json` |
| Insider Ownership | DEF 14A Proxy | yfinance | `artifacts/{ticker}/profile/management_team.json` |
| Board Composition | DEF 14A Proxy | 10-K | `artifacts/{ticker}/profile/management_team.json` |

## Financial Statements

| Field | Primary XBRL Tag | Fallback Tags |
|-------|-------------------|---------------|
| Revenue | `RevenueFromContractWithCustomerExcludingAssessedTax` | `Revenues`, `SalesRevenueNet` |
| Cost of Revenue | `CostOfRevenue` | `CostOfGoodsAndServicesSold` |
| Gross Profit | `GrossProfit` | — |
| R&D | `ResearchAndDevelopmentExpense` | — |
| SG&A | `SellingGeneralAndAdministrativeExpense` | `GeneralAndAdministrativeExpense` |
| Operating Income | `OperatingIncomeLoss` | — |
| Net Income | `NetIncomeLoss` | `ProfitLoss` |
| EPS (Diluted) | `EarningsPerShareDiluted` | — |
| Total Assets | `Assets` | — |
| Total Liabilities | `Liabilities` | — |
| Stockholders' Equity | `StockholdersEquity` | — |
| Cash from Operations | `NetCashProvidedByUsedInOperatingActivities` | — |
| CapEx | `PaymentsToAcquirePropertyPlantAndEquipment` | — |
| Free Cash Flow | Calculated: CFO - CapEx | — |

## Derived Metrics

| Metric | Formula |
|--------|---------|
| Gross Margin | Gross Profit / Revenue |
| Operating Margin | Operating Income / Revenue |
| Net Margin | Net Income / Revenue |
| FCF Margin | Free Cash Flow / Revenue |
| Revenue Growth | (Rev_t - Rev_t-1) / Rev_t-1 |
| ROE | Net Income / Stockholders' Equity |
| ROA | Net Income / Total Assets |
| ROIC | NOPAT / Invested Capital |
| Current Ratio | Current Assets / Current Liabilities |
| Debt/Equity | (Short-term Debt + Long-term Debt) / Equity |

## Competitive Landscape (NEW)

| Field | Primary Source | Fallback | Storage |
|-------|---------------|----------|---------|
| Competitor Names | 10-K Item 1 (competitors mentioned) | Web search, agent knowledge | `artifacts/{ticker}/profile/competitive_landscape.json` |
| Market Share | Industry reports, web search | Agent estimate | `artifacts/{ticker}/profile/competitive_landscape.json` |
| Competitive Positioning | 10-K Item 1 + MD&A | Web search | `artifacts/{ticker}/profile/competitive_landscape.json` |
| TAM/SAM/SOM | Industry reports, 10-K | Web search | `artifacts/{ticker}/profile/competitive_landscape.json` |

## Comparable Company Analysis (NEW)

| Field | Source | Notes |
|-------|--------|-------|
| Peer List | yfinance `get_peers()` + 10-K competitors | 5-8 public peers |
| Peer Market Cap | yfinance `get_stock_info()` | Real-time |
| Peer Revenue Growth | yfinance | LTM |
| Peer Margins | yfinance | LTM |
| Peer Multiples (P/E, EV/EBITDA, P/S) | yfinance | Real-time |
| Statistical Summary | Calculated | Median, Mean, Min, Max |

## Risks & Opportunities (NEW)

| Field | Primary Source | Storage |
|-------|---------------|---------|
| Risk Factors | 10-K Item 1A | `artifacts/{ticker}/profile/risk_factors.json` |
| Opportunities | 10-K MD&A (Item 7), press releases | `artifacts/{ticker}/profile/risk_factors.json` |
| Catalysts | Earnings calls, web search | In report directly |

## Price Data

| Field | Primary Source | Fallback |
|-------|---------------|----------|
| Daily OHLCV | Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED` | yfinance `history()` |
| Latest Quote | yfinance `get_current_price()` | Alpha Vantage `GLOBAL_QUOTE` |
| 52-Week High/Low | yfinance | — |
| Beta | yfinance | — |

## SEC API Endpoints

| Data | URL Pattern |
|------|------------|
| Company Submissions | `https://data.sec.gov/submissions/CIK{cik_padded}.json` |
| XBRL Company Facts | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json` |
| Ticker → CIK Map | `https://www.sec.gov/files/company_tickers.json` |
| Filing Documents | `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/` |

All SEC APIs require `User-Agent` header with contact email and are rate-limited to 10 requests/second.

## File Storage Layout

```
data/
├── raw/{ticker}/
│   ├── company_facts.json          # XBRL structured data (from SEC API)
│   ├── 10-K_2026_01.htm            # Annual report HTML
│   └── 10-Q_2025_09.htm            # Quarterly report HTML
├── artifacts/{ticker}/
│   └── profile/
│       ├── 10k_raw_sections.json    # Extracted section text (by ETL)
│       ├── financial_data.json      # Combined financials, split-adjusted (agent via MCP)
│       ├── company_overview.json    # AI-parsed business description
│       ├── management_team.json     # AI-parsed executive bios
│       ├── risk_factors.json        # AI-parsed risks + opportunities
│       ├── competitive_landscape.json # Competitors, moat, market position
│       ├── financial_segments.json  # Revenue by segment/geography
│       ├── investment_thesis.json   # Bull case + opportunities
│       ├── comps_table.json         # Comparable company analysis
│       └── company_profile.md       # Final generated report
```
