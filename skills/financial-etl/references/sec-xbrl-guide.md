# SEC XBRL API Guide

## Overview

The SEC provides free, structured financial data through its XBRL (eXtensible Business Reporting Language) APIs. This is the same underlying data that companies report in their 10-K and 10-Q filings, but in machine-readable JSON format.

## Key Endpoints

### 1. Company Tickers
```
GET https://www.sec.gov/files/company_tickers.json
```
Returns a mapping of all publicly traded companies with their ticker symbols and CIK numbers. Use this to resolve a ticker (e.g., "NVDA") to a CIK (e.g., "1045810").

### 2. Company Submissions
```
GET https://data.sec.gov/submissions/CIK{cik_padded_10_digits}.json
```
Returns company metadata and a list of all filings (10-K, 10-Q, 8-K, etc.). Useful for:
- Company name, SIC code, fiscal year end
- Filing dates and accession numbers
- Primary document URLs

### 3. Company Facts (MAIN DATA SOURCE)
```
GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded_10_digits}.json
```
Returns ALL structured financial data ever reported by the company. This is the gold mine.

Structure:
```json
{
  "cik": 1045810,
  "entityName": "NVIDIA CORP",
  "facts": {
    "us-gaap": {
      "Revenues": {
        "label": "Revenues",
        "units": {
          "USD": [
            {
              "val": 60922000000,
              "fy": 2024,
              "fp": "FY",
              "form": "10-K",
              "filed": "2024-02-21",
              "end": "2024-01-28"
            }
          ]
        }
      },
      "NetIncomeLoss": { ... },
      "Assets": { ... }
    }
  }
}
```

## Key Fields in Each Data Point

| Field | Description |
|-------|-------------|
| `val` | The numerical value |
| `fy` | Fiscal year |
| `fp` | Fiscal period: `FY` (annual), `Q1`-`Q4` (quarterly) |
| `form` | Filing type: `10-K` (annual), `10-Q` (quarterly) |
| `filed` | Date the filing was submitted to SEC |
| `end` | Period end date |

## Common Gotchas

1. **CIK padding**: Must be padded to 10 digits with leading zeros (e.g., `CIK0001045810`)
2. **Duplicate values**: Same fact may appear in amendments — always pick the most recently filed value
3. **Tag inconsistency**: Different companies use different tags for the same concept
4. **Annual vs Quarterly**: Filter on `fp` field — `FY` for annual, `Q1`-`Q4` for quarterly
5. **10-K vs 10-Q**: Annual filings (`form=10-K`) contain full-year data, quarterly (`form=10-Q`) contain quarter-specific data
6. **Units**: Most values are in USD, but EPS is in `USD/shares` and share counts are in `shares`

## Rate Limits

- Maximum 10 requests per second
- Must include `User-Agent` header with name and email
- Example: `User-Agent: PersonalFinanceApp john@example.com`

## SIC Codes (Sector Classification)

SEC uses Standard Industrial Classification (SIC) codes. Common mappings for AI sector:
- `3674` - Semiconductors (NVDA, AMD, AVGO)
- `7372` - Prepackaged Software (MSFT, CRM)
- `7371` - Computer Programming (GOOG, META)
- `5045` - Computers and Peripherals (DELL)
- `3672` - Printed Circuit Boards (SMCI)
