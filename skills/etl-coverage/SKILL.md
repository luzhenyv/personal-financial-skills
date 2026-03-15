---
name: etl-coverage
description: ETL coverage audit skill. Checks for missing values in financial statements
  (income, balance, cash flow), diagnoses whether NULLs come from absent SEC
  data or unmapped XBRL tags, and recommends fixes. Run this after ingesting
  new companies to validate data quality.
---

# ETL Coverage Check Skill

Check the ETL data-coverage for companies already ingested into PostgreSQL.
For every NULL cell the skill determines **why** the value is missing and what
(if anything) to do about it.

## When to use

| Trigger | Example |
|---|---|
| After ingesting new companies | "I just added AAPL — check the ETL coverage" |
| Periodic quality audit | "Run ETL coverage across all companies" |
| Debugging a specific field | "Why is `depreciation_amortization` NULL for KO 2024?" |
| Expanding parser mappings | "Find unmapped XBRL tags for all tickers" |

---

## Task 1 — Run Coverage Check

Run the check script. It queries the DB **and** the cached SEC XBRL JSON for
every company to classify each NULL.

```bash
# Single ticker
uv run python skills/etl-coverage/scripts/check_coverage.py --ticker AAPL

# All companies in the DB
uv run python skills/etl-coverage/scripts/check_coverage.py

# Summary table only
uv run python skills/etl-coverage/scripts/check_coverage.py --summary
```

**Output file**: `data/artifacts/_etl/coverage_report.json`

### NULL classifications

| Status | Meaning | Action |
|---|---|---|
| `ok` | Field is populated | None |
| `no_data` | Company genuinely does not report this item in SEC XBRL | **Skip** — this is expected |
| `optional` | Field is commonly absent for the company's sector | **Skip** — legitimate |
| `unmapped` | XBRL data exists but our parser does not map it | **Fix** — add tag to `xbrl_parser.py` |

---

## Task 2 — Analyze Results

Read the JSON report (or stdout) and focus on `unmapped` entries.

For each unmapped cell the report includes:
- `mapped_tags_with_data` — tags already in `xbrl_parser.py` that **do** have
  annual data for the year but were not picked by the parser (likely a bug in
  `_resolve_tag_for_year`).
- `candidate_new_tags` — XBRL concept tags found by keyword search in the raw
  facts JSON that are **not** in any mapping list yet.

### Decision matrix

| Unmapped type | Root cause | Fix |
|---|---|---|
| `mapped_tags_with_data` is non-empty | Parser has the tag but mis-selected | Debug `_resolve_tag_for_year()` in `src/etl/xbrl_parser.py` — check fiscal-year/quarter matching logic |
| `candidate_new_tags` is non-empty | New XBRL concept not in our mapping | Add the tag(s) to the appropriate `*_TAGS` dict in `src/etl/xbrl_parser.py` |
| Both empty, status=`no_data` | Company doesn't file this item | No fix — document as expected |

---

## Task 3 — Fix Unmapped Tags (if any)

1. Open `src/etl/xbrl_parser.py`
2. Find the relevant mapping dict (`INCOME_STATEMENT_TAGS`, `BALANCE_SHEET_TAGS`,
   or `CASH_FLOW_TAGS`)
3. Append the new tag to the **end** of the candidate list for the target field
   (order = priority; first match wins)
4. Re-ingest the affected ticker(s):
   ```bash
   uv run python -m src.etl.pipeline ingest {TICKER} --years 5
   ```
5. Re-run coverage check to verify the fix:
   ```bash
   uv run python skills/etl-coverage/scripts/check_coverage.py --ticker {TICKER}
   ```
6. Repeat until `unmapped` count is 0 (or only company-specific anomalies remain).

---

## Task 4 — Generate Conclusion

After analysis, produce a summary that states for each company:

```
{TICKER} ({SECTOR}):
  Coverage: XX.X% OK, XX.X% no_data, XX.X% optional, XX.X% unmapped
  Conclusion: {one of the below}
    ✅ Full coverage — all parseable XBRL data is mapped
    ⚠  Unmapped fields — N fields need new XBRL tag mappings (list them)
    ℹ  Expected gaps — remaining NULLs are sector-appropriate
```

If all companies show 0 unmapped → **"ETL parser is fully aligned with
available SEC XBRL data."**

---

## Key Files

| File | Purpose |
|---|---|
| `skills/etl-coverage/scripts/check_coverage.py` | Main analysis script |
| `src/etl/xbrl_parser.py` | XBRL tag → DB field mappings + parsing logic |
| `src/etl/pipeline.py` | Full ingestion pipeline (ingest / ingest-batch) |
| `src/db/models.py` | ORM models defining all financial statement columns |
| `data/artifacts/_etl/coverage_report.json` | Latest coverage report (machine-readable) |

## Reference docs

| File | Content |
|---|---|
| `skills/etl-coverage/references/field-definitions.md` | Every DB field with its meaning and expected XBRL sources |
| `skills/etl-coverage/references/sector-exceptions.md` | Which fields are legitimately NULL by sector |
| `skills/etl-coverage/references/troubleshooting.md` | Common issues and how to resolve them |
