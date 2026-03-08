# Financial Data ETL

## Skill Metadata
- **Name**: financial-etl
- **Description**: Fetch financial data from SEC EDGAR XBRL API, parse, and store in PostgreSQL
- **Trigger**: User asks to "add a company", "load data for {ticker}", "refresh {ticker}"
- **Output**: Rows in PostgreSQL tables: `companies`, `income_statements`, `balance_sheets`, `cash_flow_statements`, `financial_metrics`, `sec_filings`

## When to Use
- Adding a new company to the database for the first time
- Refreshing data after a new 10-K or 10-Q filing
- Bulk loading a watchlist of companies
- Before running any analysis skill (company-profile, dcf, comps, etc.)

## Data Sources
- **SEC EDGAR Company Facts API**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`
- **SEC EDGAR Submissions API**: `https://data.sec.gov/submissions/CIK{cik}.json`
- **SEC Company Tickers**: `https://www.sec.gov/files/company_tickers.json`
- **Alpha Vantage**: Daily adjusted prices (optional, requires API key)

## Important Constraints
- SEC rate limit: max 10 requests/second — code adds 120ms delay between calls
- SEC requires `User-Agent` header with contact email (set in `.env`)
- Alpha Vantage free tier: 25 requests/day
- XBRL data can have inconsistent tag names across companies — parser tries multiple fallback tags

## Workflow

### Step 1: Resolve Ticker → CIK
```python
from src.etl.sec_client import ticker_to_cik
cik = ticker_to_cik("NVDA")  # Returns "1045810"
```

### Step 2: Run Full Pipeline
```python
from src.etl.pipeline import ingest_company

result = ingest_company("NVDA", years=5, include_prices=True)
print(result)
# {
#   "ticker": "NVDA",
#   "company": True,
#   "income_statements": 5,
#   "balance_sheets": 5,
#   "cash_flow_statements": 5,
#   "financial_metrics": 5,
#   "sec_filings": 15,
#   "daily_prices": 100,
#   "errors": []
# }
```

### Step 3: Verify Data Quality
```sql
-- Check what was loaded
SELECT fiscal_year, revenue, net_income, operating_income
FROM income_statements WHERE ticker = 'NVDA' ORDER BY fiscal_year;

-- Check for missing fields
SELECT fiscal_year,
  CASE WHEN revenue IS NULL THEN 'MISSING' ELSE 'OK' END as revenue_check,
  CASE WHEN net_income IS NULL THEN 'MISSING' ELSE 'OK' END as ni_check,
  CASE WHEN operating_income IS NULL THEN 'MISSING' ELSE 'OK' END as oi_check
FROM income_statements WHERE ticker = 'NVDA';
```

### Step 4: Bulk Load (Watchlist)
```python
tickers = ["NVDA", "AMD", "MSFT", "GOOG", "META", "AMZN", "AVGO", "TSM", "SMCI", "CRM"]
for t in tickers:
    result = ingest_company(t, years=5, include_prices=False)
    print(f"{t}: {result['income_statements']} years loaded, errors: {result['errors']}")
```

## XBRL Tag Mapping
See `references/schema-reference.md` for the complete XBRL tag → database column mapping.

Key challenge: Different companies use different XBRL tags for the same concept.
Example for Revenue:
1. `RevenueFromContractWithCustomerExcludingAssessedTax` (most common post-ASC 606)
2. `Revenues` (common fallback)
3. `SalesRevenueNet` (older filings)

The parser tries each candidate tag in order until it finds data.

## Error Handling
- Missing XBRL tags: logged as warnings, field set to NULL
- SEC API errors: raises exception, caught by pipeline, logged in result["errors"]
- Duplicate data: uses UPSERT (ON CONFLICT DO UPDATE) — safe to re-run

## Reference Files
- `references/schema-reference.md` — Full XBRL tag → DB column mapping
- `references/sec-xbrl-guide.md` — How SEC XBRL API works
