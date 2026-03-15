# Troubleshooting Guide

Common issues encountered during ETL coverage analysis and how to fix them.

---

## 1. "unmapped" — Tags exist in XBRL but parser doesn't use them

**Symptom**: Coverage report shows `unmapped` status with
`candidate_new_tags` populated.

**Fix**:
1. Open `src/etl/xbrl_parser.py`
2. Find the correct mapping dict:
   - Income fields → `INCOME_STATEMENT_TAGS`
   - Balance fields → `BALANCE_SHEET_TAGS`
   - Cash flow fields → `CASH_FLOW_TAGS`
3. Add the new tag to the **end** of the list for the target field
4. Re-ingest: `uv run python -m src.etl.pipeline ingest {TICKER} --years 5`
5. Re-check: `uv run python skills/etl-coverage/scripts/check_coverage.py --ticker {TICKER}`

**Example**:
```python
# Before
"revenue": [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
],

# After — added a new tag at the end
"revenue": [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",  # Used by older filings
],
```

---

## 2. "unmapped" — `mapped_tags_with_data` is non-empty

**Symptom**: The parser already has the tag in its mapping, AND the tag has
data for the year, but the DB cell is still NULL.

**Root cause**: Usually a bug in `_resolve_tag_for_year()` or `_pick_annual()`.
Common reasons:
- The `fp` (fiscal period) filter is too strict — some companies use
  non-standard period labels
- The `form` filter excludes valid filings (e.g., company files an amended
  10-K/A instead of 10-K)
- The `min_year` filter accidentally excludes the data

**Fix**: Debug by running in Python:
```python
from src.etl.xbrl_parser import _extract_fact_values
from src.etl.sec_client import get_company_facts_cached, ticker_to_cik

cik = ticker_to_cik("AAPL")
facts = get_company_facts_cached("AAPL", cik)
vals = _extract_fact_values(facts, "RevenueFromContractWithCustomerExcludingAssessedTax", "USD", 2020)
for v in vals:
    print(v)
```

Check if the expected year/period data appears. If it does, trace through
`_pick_annual()` to see why it's not selected.

---

## 3. Financial companies show many "no_data" cells

**Expected behavior**. Banks (JPM, GS, C) and insurance companies use
fundamentally different financial reporting structures:
- No COGS / gross profit
- Revenue = net interest income + non-interest income
- Operating expense = non-interest expense

The parser maps `NoninterestExpense` → `operating_expenses` and
`RevenuesNetOfInterestExpense` → `revenue`, but many other fields
will legitimately be NULL.

---

## 4. `free_cash_flow` is always NULL

`free_cash_flow` is a **derived field**: `CFO − |CapEx|`. It is computed in
`parse_cash_flow()` only if both `cash_from_operations` and
`capital_expenditure` are non-NULL. If either is missing, FCF will be NULL.

Fix by ensuring both source fields are mapped first.

---

## 5. Derived fields show NULL even though components exist

Three fields are computed from other fields:
- `gross_profit` = `revenue` − `cost_of_revenue`
- `operating_expenses` = `gross_profit` − `operating_income`
- `total_liabilities` = `total_assets` − `total_stockholders_equity`

If the derived field is NULL, check whether the component fields are also NULL.
The derivation only triggers when the direct XBRL tag (e.g., `GrossProfit`)
returns no data.

---

## 6. Re-ingestion doesn't pick up parser changes

After editing `xbrl_parser.py`, you must re-ingest:
```bash
uv run python -m src.etl.pipeline ingest {TICKER} --years 5
```

The pipeline **upserts** (inserts or updates) so existing rows will be
updated with the newly parsed values. No need to delete existing data first.

---

## 7. SEC rate limiting (HTTP 429) during analysis

The coverage script calls `sec_client.get_company_facts_cached()` which uses
the local file cache (`data/raw/{TICKER}/company_facts.json`). If the file
doesn't exist yet, it makes a network request.

If you hit rate limits:
- Wait 60 seconds and retry
- Or run `ingest` first (which caches the facts), then run coverage check
