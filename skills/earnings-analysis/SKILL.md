---
name: earnings-analysis
description: Create post-earnings analysis reports for companies under coverage. Analyzes quarterly results with beat/miss analysis, segment breakdown, margin trends, guidance changes, and thesis impact assessment. Triggers on "earnings analysis for [ticker]", "quarterly update [ticker]", "Q1/Q2/Q3/Q4 results [ticker]", or "post-earnings [ticker]". Auto-runs thesis health check and recommends hold/add/trim/exit.
---

# Earnings Analysis

Professional post-earnings analysis — the most important reactive skill. When a company reports, assess thesis impact within 24 hours.

## When to Use

- "Earnings analysis for NVDA"
- "Analyze NVDA Q4 2024 results"
- "Post-earnings update for AAPL"
- After a new 10-Q is detected by the ETL pipeline

**Prerequisite**: Company must be ingested (`GET /api/companies/{TICKER}` returns 200). If 404, tell the user:

> I don't have financial data for {TICKER} yet. Please run ETL first:
> ```bash
> uv run python -m pfs.etl.pipeline ingest {TICKER} --years 5
> ```

## Artifacts

Output goes to `data/artifacts/{TICKER}/earnings/`:

```
data/artifacts/{ticker}/earnings/
  Q4_2024.json              # Structured earnings data (beat/miss, segments, guidance)
  Q4_2024_analysis.md       # Narrative analysis report
```

Every JSON artifact includes `"schema_version": "1.0"`.

## Workflow (4 Tasks)

### Task 1: Data Collection (Script)

Collect all financial data needed for the earnings analysis.

```bash
uv run python skills/earnings-analysis/scripts/collect_earnings.py {TICKER} [--quarter Q4] [--year 2024]
```

**What the script does:**
1. Calls `GET /api/companies/{TICKER}` — verify company exists
2. Calls `GET /api/financials/{TICKER}/quarterly?quarters=8` — last 8 quarters for trends
3. Calls `GET /api/financials/{TICKER}/income-statements?years=2` — annual comparison
4. Calls `GET /api/financials/{TICKER}/metrics` — margin and growth metrics
5. Calls `GET /api/financials/{TICKER}/segments` — segment breakdown
6. Calls `GET /api/filings/{TICKER}?form_type=10-Q` — latest 10-Q filing metadata
7. Calls `GET /api/financials/{TICKER}/prices?period=3m` — recent price action

**Freshness check** (⚠️ Critical):
- Verify the latest quarterly data matches the quarter being analyzed
- If data is stale, warn the user to re-run ETL sync

**Output**: `data/artifacts/{TICKER}/earnings/{QUARTER}_{YEAR}_raw.json`

### Task 2: Beat/Miss Analysis (AI + Script)

Analyze whether the company beat or missed on key metrics.

**AI analyzes** (after reading raw data from Task 1):

| Metric | What to assess |
|--------|---------------|
| Revenue | Total vs prior quarter and YoY |
| EPS | Diluted EPS vs prior quarter and YoY |
| Gross margin | Expansion or contraction, direction vs trend |
| Operating margin | Leverage and cost discipline |
| Segment revenue | Which segments drove the beat/miss |
| Free cash flow | Operating CF minus CapEx trends |

**For each metric, document:**
- Actual result
- Prior quarter result (QoQ change)
- Year-ago quarter result (YoY change)
- Direction vs multi-quarter trend
- Whether result is positive or negative for the thesis

**Guidance analysis:**
- Did management guide above/below/in-line with prior guidance?
- Any new or withdrawn guidance?
- Tone of management commentary on outlook

### Task 3: Thesis Impact (AI)

Connect the earnings results to the investment thesis.

**If thesis exists** (`data/artifacts/{TICKER}/thesis/thesis.json`):
- Score each thesis assumption against the quarter's results
- Use thesis-tracker scoring: ✓ strengthened / ⚠️ weakened / ✗ broken / — no change
- Compute updated thesis health score
- Recommend: **Hold / Add / Trim / Exit**

**If no thesis exists:**
- Note that no formal thesis is tracked
- Provide a standalone assessment of whether results are positive/negative for a long position
- Suggest creating a thesis: `uv run python skills/thesis-tracker/scripts/thesis_cli.py create {TICKER} --interactive`

### Task 4: Report Generation (Script)

Combine all analysis into a markdown report.

```bash
uv run python skills/earnings-analysis/scripts/generate_earnings_report.py {TICKER} [--quarter Q4] [--year 2024]
```

**Report structure** (markdown):

```markdown
# {COMPANY} — {QUARTER} {YEAR} Earnings Analysis

## Quick Summary
- **Quarter**: Q4 FY2024
- **Revenue**: $X.XB (YoY +X%)
- **EPS**: $X.XX (YoY +X%)
- **Thesis Impact**: Strengthened / Weakened / Unchanged
- **Recommendation**: Hold / Add / Trim / Exit

## Beat/Miss Summary
| Metric | Result | QoQ Change | YoY Change | Assessment |
|--------|--------|------------|------------|------------|
| Revenue | ... | ... | ... | ✓/⚠️/✗ |
| ...     | ... | ... | ... | ... |

## Revenue Breakdown by Segment
...

## Margin Analysis
...

## Guidance Update
...

## Thesis Impact Assessment
(If thesis exists — assumption-by-assumption scoring)

## Key Takeaways
1. ...
2. ...
3. ...

## Data Sources
- REST API: /api/financials/{TICKER}/quarterly
- SEC Filing: 10-Q filed {DATE}
- Analysis date: {TODAY}
```

**Output files:**
- `data/artifacts/{TICKER}/earnings/{QUARTER}_{YEAR}.json` — structured data
- `data/artifacts/{TICKER}/earnings/{QUARTER}_{YEAR}_analysis.md` — narrative report

**Post-report actions:**
- If thesis exists, auto-trigger thesis update via:
  ```bash
  uv run python skills/thesis-tracker/scripts/thesis_cli.py update {TICKER} --interactive
  ```
- Upsert report to DB via `POST /api/analysis/reports`

## REST API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /api/companies/{TICKER}` | Verify company exists |
| `GET /api/financials/{TICKER}/quarterly?quarters=8` | Quarterly trends |
| `GET /api/financials/{TICKER}/income-statements?years=2` | Annual comparison |
| `GET /api/financials/{TICKER}/balance-sheets?years=2&quarterly=true` | Quarterly balance sheet |
| `GET /api/financials/{TICKER}/cash-flows?years=2&quarterly=true` | Quarterly cash flows |
| `GET /api/financials/{TICKER}/metrics` | Margin and growth metrics |
| `GET /api/financials/{TICKER}/segments` | Segment revenue breakdown |
| `GET /api/filings/{TICKER}?form_type=10-Q` | Latest 10-Q metadata |
| `GET /api/financials/{TICKER}/prices?period=3m` | Post-earnings price action |
| `POST /api/analysis/reports` | Persist report to DB |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/collect_earnings.py` | Task 1 — fetch data from REST API, write raw JSON |
| `scripts/generate_earnings_report.py` | Task 4 — assemble markdown from JSON + AI analysis |
| `scripts/artifact_io.py` | Local copy of JSON/Markdown I/O helpers |

## Key Differences from Anthropic equity-research Version

| Aspect | This skill | Anthropic version |
|--------|-----------|-------------------|
| **Output** | JSON + Markdown artifacts | DOCX report (8-12 pages) |
| **Charts** | None (Streamlit handles viz) | 8-12 embedded charts |
| **Thesis integration** | Built-in thesis impact + auto-update | No thesis tracking |
| **Data source** | REST API (database) | Web search + SEC |
| **Audience** | Personal use via dashboard | Client distribution |
| **Turnaround** | Minutes (automated) | 24-48 hours |

## Data Source Priority

```
1. REST API (database)   ← primary, already validated by ETL
2. Local SEC files       ← data/raw/{ticker}/ for 10-Q text
3. Web search            ← last resort for qualitative context
```
