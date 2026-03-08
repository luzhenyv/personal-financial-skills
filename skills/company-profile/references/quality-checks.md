# Quality Checks

Run these checks after completing all 4 tasks for a given ticker.

## Data Completeness

- [ ] `data/raw/{TICKER}/10-K_*.htm` exists (raw annual filing downloaded)
- [ ] `data/processed/{TICKER}/10k_raw_sections.json` exists with non-empty sections
- [ ] All 6 JSON files exist in `data/processed/{TICKER}/`
- [ ] At least 3 years of annual data in all DB tables
- [ ] Revenue figures in correct magnitude (billions vs millions — verify against XBRL)

## Stock Split Adjustment

- [ ] If the company has had stock splits, verify `stock_splits.json` exists
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

## Output

- [ ] Report saved to both filesystem and database

## Verification Query

```sql
SELECT fiscal_year, revenue/1e9 AS rev_b, gross_margin*100 AS gm_pct
FROM income_statements i
JOIN financial_metrics m USING (ticker, fiscal_year)
WHERE i.ticker = '{ticker}' AND i.fiscal_quarter IS NULL
ORDER BY fiscal_year;
```

Require **at least 3 years** of annual data before proceeding.
