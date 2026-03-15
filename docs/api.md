# API Reference

The Personal Finance API is a FastAPI application. The interactive Swagger UI is available at `http://localhost:8000/docs` when the server is running.

**Base URL:** `http://localhost:8000`

All responses are JSON unless noted otherwise. Endpoints that accept a `{ticker}` path parameter normalize the ticker to uppercase internally.

---

## Health

### `GET /health`

Returns the server status.

**Response**

```json
{ "status": "ok" }
```

---

## Companies

### `GET /api/companies/`

List all ingested companies, with optional sector filtering and pagination.

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `sector` | string | — | Filter by sector name (exact match) |
| `limit` | integer | `50` | Max results to return (1–500) |
| `offset` | integer | `0` | Number of records to skip |

**Response** — array of company objects

```json
[
  {
    "id": 1,
    "cik": "0001045810",
    "ticker": "NVDA",
    "name": "NVIDIA Corporation",
    "sector": "Technology",
    "industry": "Semiconductors",
    "sic_code": "3674",
    "exchange": "NASDAQ",
    "fiscal_year_end": "01-31",
    "market_cap": 3200000000000,
    "employee_count": 36000,
    "headquarters": "Santa Clara, CA",
    "description": "...",
    "website": "https://www.nvidia.com",
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-11-15T10:00:00"
  }
]
```

---

### `GET /api/companies/{ticker}`

Get a single company by ticker symbol.

**Path Parameters**

| Parameter | Description |
|---|---|
| `ticker` | Company ticker symbol (e.g. `NVDA`) |

**Response** — single company object (same shape as the list response above)

**Errors**

| Status | Description |
|---|---|
| `404` | Company not found — not yet ingested |

---

## ETL

### `POST /api/etl/ingest`

Trigger a full company ingestion in a background thread. Returns immediately with a tracking ID; the ingestion continues asynchronously.

**Request Body**

```json
{
  "ticker": "NVDA",
  "years": 5,
  "quarterly": false
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `ticker` | string | required | Company ticker symbol |
| `years` | integer | `5` | Number of years of filings to fetch |
| `quarterly` | boolean | `false` | Whether to also ingest quarterly (10-Q) filings |

**Response**

```json
{
  "message": "Ingestion started for NVDA",
  "etl_run_id": 42,
  "ticker": "NVDA"
}
```

Use `etl_run_id` with `GET /api/etl/runs` to check run status.

---

### `POST /api/etl/sync-prices`

Sync daily price history for one or more companies. If `tickers` is omitted or null, all ingested companies are synced.

**Request Body**

```json
{
  "tickers": ["NVDA", "AAPL"]
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `tickers` | array of strings | `null` | Tickers to sync; omit to sync all companies |

**Response**

```json
{
  "message": "Price sync completed",
  "results": { ... }
}
```

---

### `GET /api/etl/runs`

Query ETL run history with optional filters.

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ticker` | string | — | Filter by ticker symbol |
| `status` | string | — | Filter by status (`running`, `completed`, `failed`) |
| `limit` | integer | `20` | Max results to return (1–100) |

**Response** — array of ETL run objects, ordered by `started_at` descending

```json
[
  {
    "id": 42,
    "ticker": "NVDA",
    "run_type": "full_ingest",
    "status": "completed",
    "started_at": "2025-11-15T10:00:00",
    "completed_at": "2025-11-15T10:05:30",
    "income_statements": 5,
    "balance_sheets": 5,
    "cash_flow_statements": 5,
    "financial_metrics": 5,
    "revenue_segments": 12,
    "daily_prices": 1260,
    "sec_filings": 20,
    "filings_downloaded": 10,
    "errors": [],
    "metadata": {}
  }
]
```

---

## Filings

### `GET /api/filings/{ticker}`

List SEC filings for a company, ordered by filing date descending.

**Path Parameters**

| Parameter | Description |
|---|---|
| `ticker` | Company ticker symbol |

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `form_type` | string | — | Filter by form type (e.g. `10-K`, `10-Q`, `8-K`) |

**Response** — array of filing objects

```json
[
  {
    "id": 1,
    "ticker": "NVDA",
    "cik": "0001045810",
    "accession_number": "0001045810-25-000010",
    "filing_type": "10-K",
    "filing_date": "2025-02-28",
    "reporting_date": "2025-01-26",
    "primary_doc_url": "https://www.sec.gov/...",
    "xbrl_url": "https://www.sec.gov/...",
    "is_processed": true,
    "processed_at": "2025-03-01T00:00:00",
    "created_at": "2025-03-01T00:00:00",
    "local_path": "/path/to/data/raw/NVDA/10-K_2025_01.htm"
  }
]
```

The `local_path` field is `null` when the filing HTML has not been downloaded locally.

**Errors**

| Status | Description |
|---|---|
| `404` | Company not found |

---

### `GET /api/filings/{ticker}/{filing_id}`

Get a single SEC filing by its database ID.

**Path Parameters**

| Parameter | Description |
|---|---|
| `ticker` | Company ticker symbol |
| `filing_id` | Integer filing ID (from the filings list) |

**Response** — single filing object (same shape as the list response above)

**Errors**

| Status | Description |
|---|---|
| `404` | Filing not found |

---

### `GET /api/filings/{ticker}/{filing_id}/content`

Stream the raw HTML of a filing.

The server tries sources in order:
1. Local file at `data/raw/{ticker}/{form}_{date}.htm`
2. Proxied from SEC EDGAR via `primary_doc_url`

**Path Parameters**

| Parameter | Description |
|---|---|
| `ticker` | Company ticker symbol |
| `filing_id` | Integer filing ID |

**Response** — `text/html` stream

**Errors**

| Status | Description |
|---|---|
| `404` | Filing not found, or no content source available |
| `502` | Failed to fetch content from SEC EDGAR |

---

## Financials

All financials endpoints require the company to be ingested. Annual data is returned by default; pass `quarterly=true` for quarterly periods. Results are ordered chronologically (oldest first).

### `GET /api/financials/{ticker}/income-statements`

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `years` | integer | `5` | Number of periods to return (1–20) |
| `quarterly` | boolean | `false` | Return quarterly periods instead of annual |

**Response fields** (per record): `id`, `ticker`, `fiscal_year`, `fiscal_quarter`, `filing_type`, `filing_date`, `revenue`, `cost_of_revenue`, `gross_profit`, `research_and_development`, `selling_general_admin`, `depreciation_amortization`, `operating_expenses`, `operating_income`, `interest_expense`, `interest_income`, `other_income`, `pretax_income`, `income_tax`, `net_income`, `eps_basic`, `eps_diluted`, `shares_basic`, `shares_diluted`, `source`, `created_at`

---

### `GET /api/financials/{ticker}/balance-sheets`

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `years` | integer | `5` | Number of periods to return (1–20) |
| `quarterly` | boolean | `false` | Return quarterly periods instead of annual |

**Response fields** (per record): `id`, `ticker`, `fiscal_year`, `fiscal_quarter`, `filing_type`, `filing_date`, `cash_and_equivalents`, `short_term_investments`, `accounts_receivable`, `inventory`, `total_current_assets`, `property_plant_equipment`, `goodwill`, `intangible_assets`, `total_assets`, `accounts_payable`, `deferred_revenue`, `short_term_debt`, `total_current_liabilities`, `long_term_debt`, `total_liabilities`, `common_stock`, `retained_earnings`, `total_stockholders_equity`, `source`, `created_at`

---

### `GET /api/financials/{ticker}/cash-flows`

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `years` | integer | `5` | Number of periods to return (1–20) |
| `quarterly` | boolean | `false` | Return quarterly periods instead of annual |

**Response fields** (per record): `id`, `ticker`, `fiscal_year`, `fiscal_quarter`, `filing_type`, `filing_date`, `net_income`, `depreciation_amortization`, `stock_based_compensation`, `change_in_working_capital`, `cash_from_operations`, `capital_expenditure`, `acquisitions`, `purchases_of_investments`, `sales_of_investments`, `cash_from_investing`, `debt_issuance`, `debt_repayment`, `share_repurchase`, `dividends_paid`, `cash_from_financing`, `net_change_in_cash`, `free_cash_flow`, `source`, `created_at`

---

### `GET /api/financials/{ticker}/metrics`

Returns computed financial metrics for annual periods, ordered chronologically.

**Response fields** (per record): `id`, `ticker`, `fiscal_year`, `fiscal_quarter`, `gross_margin`, `operating_margin`, `ebitda_margin`, `net_margin`, `fcf_margin`, `revenue_growth`, `operating_income_growth`, `net_income_growth`, `eps_growth`, `roe`, `roa`, `roic`, `debt_to_equity`, `current_ratio`, `quick_ratio`, `dso`, `dio`, `dpo`, `ebitda`, `pe_ratio`, `ps_ratio`, `pb_ratio`, `ev_to_ebitda`, `fcf_yield`, `calculated_at`

---

### `GET /api/financials/{ticker}/prices`

Returns daily price history.

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `start` | date (`YYYY-MM-DD`) | — | Start date (inclusive). Overrides `period`. |
| `end` | date (`YYYY-MM-DD`) | — | End date (inclusive) |
| `period` | string | `1y` | Lookback period when `start` is not set. One of `1m`, `3m`, `6m`, `1y`, `2y`, `5y` |

**Response** — array of daily price objects, ordered by date ascending

```json
[
  {
    "id": 1,
    "ticker": "NVDA",
    "date": "2025-11-15",
    "open_price": "145.2300",
    "high_price": "148.9100",
    "low_price": "144.5000",
    "close_price": "147.3200",
    "adjusted_close": "147.3200",
    "volume": 42000000,
    "created_at": "2025-11-15T20:00:00"
  }
]
```

---

### `GET /api/financials/{ticker}/segments`

Returns revenue segment breakdowns (by product, geography, or channel).

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `fiscal_year` | integer | — | Filter by fiscal year |

**Response** — array of revenue segment objects

```json
[
  {
    "id": 1,
    "ticker": "NVDA",
    "fiscal_year": 2025,
    "fiscal_quarter": null,
    "segment_type": "product",
    "segment_name": "Data Center",
    "revenue": 115000000000,
    "pct_of_total": "0.8700",
    "source": "sec_xbrl",
    "created_at": "2025-03-01T00:00:00"
  }
]
```

**Errors** (all financials endpoints)

| Status | Description |
|---|---|
| `404` | Company not found — not yet ingested |

---

## Common Patterns

### Trigger ingestion then poll for completion

```bash
# 1. Start ingestion
RESPONSE=$(curl -s -X POST http://localhost:8000/api/etl/ingest \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "years": 5}')

RUN_ID=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['etl_run_id'])")

# 2. Poll run status
curl "http://localhost:8000/api/etl/runs?ticker=NVDA&limit=1"
```

### Fetch 3 years of quarterly income statements

```bash
curl "http://localhost:8000/api/financials/NVDA/income-statements?years=12&quarterly=true"
```

### Get price history for a specific date range

```bash
curl "http://localhost:8000/api/financials/NVDA/prices?start=2024-01-01&end=2024-12-31"
```

### List only 10-K filings

```bash
curl "http://localhost:8000/api/filings/NVDA?form_type=10-K"
```
