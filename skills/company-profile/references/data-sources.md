# Data Sources Reference

Maps each data field in the company profile to its source.

## Company Metadata

| Field | Source | Table / API |
|-------|--------|-------------|
| Company Name | SEC EDGAR Submissions | `companies.name` |
| Ticker | SEC Company Tickers | `companies.ticker` |
| CIK | SEC Company Tickers | `companies.cik` |
| Sector / Industry | SEC SIC Code → mapping | `companies.sector`, `companies.industry` |
| Exchange | SEC EDGAR Submissions | `companies.exchange` |
| Fiscal Year End | SEC EDGAR Submissions | `companies.fiscal_year_end` |
| Website | SEC EDGAR Submissions | `companies.website` |

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

## Price Data

| Field | Source |
|-------|--------|
| Daily OHLCV | Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED` |
| Latest Quote | Alpha Vantage `GLOBAL_QUOTE` |
| Market Cap | Calculated: Price × Shares Outstanding |

## SEC API Endpoints

| Data | URL Pattern |
|------|------------|
| Company Submissions | `https://data.sec.gov/submissions/CIK{cik_padded}.json` |
| XBRL Company Facts | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json` |
| Ticker → CIK Map | `https://www.sec.gov/files/company_tickers.json` |

All SEC APIs require `User-Agent` header with contact email and are rate-limited to 10 requests/second.
