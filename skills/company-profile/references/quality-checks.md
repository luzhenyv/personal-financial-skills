# Quality Checks

Run these checks after completing all 3 tasks for a given ticker.

## Prerequisite: ETL Data

- [ ] Company exists in REST API: `GET /api/companies/` shows the ticker
- [ ] At least 3 years of annual data: `GET /api/financials/{TICKER}/income-statements?years=3` returns data
- [ ] `data/raw/{TICKER}/10-K_*.htm` exists (raw annual filing downloaded by ETL)

## Data Completeness

- [ ] `data/artifacts/{TICKER}/profile/10k_raw_sections.json` exists with non-empty sections
- [ ] All 6 JSON files exist in `data/artifacts/{TICKER}/profile/`
- [ ] `data/artifacts/{TICKER}/profile/financial_data.json` exists (written by agent via `GET /api/financials/{TICKER}/annual`)
- [ ] Revenue figures in correct magnitude (billions vs millions — verify against REST API data)

## Stock Split Adjustment

- [ ] Call `GET /api/financials/{TICKER}/stock-splits` — verify split history is present if the company has had splits
- [ ] All per-share metrics (EPS, DPS, shares outstanding) are adjusted to current share basis
- [ ] Compare adjusted EPS against yfinance's split-adjusted values as a sanity check (should match within 1%)

## Financial Integrity

- [ ] Growth rates computed correctly: (current − prior) / prior
- [ ] Margins sanity check: gross 20–90%, operating −20% to +80%

## Research Quality

- [ ] Management team: 3–5 executives with substantive bios (not placeholder text)
- [ ] Competitive landscape: 5–8 competitors with valid tickers for comps lookup
- [ ] `comps_table.json` has actual data (not all N/A)
- [ ] Risk factors sourced from Item 1A language
- [ ] `investment_thesis.json` has 4–6 bull case items with data points
- [ ] All JSON files include `"schema_version": "1.0"` field

## Output

- [ ] Report saved to `data/artifacts/{TICKER}/profile/company_profile.md`
- [ ] Report persisted via `POST /api/analysis/reports` to `analysis_reports` table

## Verification

Use `GET /api/financials/{TICKER}/income-statements` and `GET /api/financials/{TICKER}/metrics` to cross-check revenue and margins against the report. Require **at least 3 years** of annual data before proceeding.
