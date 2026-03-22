```skill
---
name: thesis-tracker
description: Create, update, and health-check investment theses. Triggers on "create thesis for [ticker]", "update thesis for [ticker]", "thesis health check [ticker]", "is my thesis still intact", "catalyst check [ticker]", or "review my positions".
---

# Thesis Tracker

Core question: **"Is my original buy reason still valid?"**

**Storage**: `data/artifacts/{TICKER}/thesis/` — JSON files + generated markdown report. Never write to PostgreSQL; read via MCP, write artifacts only. Persist reports via MCP `save_analysis_report`.

**CLI** — one entry point, five subcommands:
```bash
THESIS=skills/thesis-tracker/scripts/thesis_cli.py

uv run python $THESIS create  {TICKER} --interactive     # Task 1
uv run python $THESIS update  {TICKER} --interactive     # Task 2
uv run python $THESIS check   {TICKER}                   # Task 3
uv run python $THESIS catalyst {TICKER} --add             # Task 4
uv run python $THESIS report  {TICKER}                   # Regenerate markdown
```

## Prerequisite

Verify financial data exists before creating a thesis:
1. MCP `list_companies` / `get_company(ticker)` — confirm ticker is ingested
2. If missing: `uv run python -m pfs.etl.pipeline ingest {TICKER} --years 5`
3. Optional: seed from `data/artifacts/{TICKER}/profile/` artifacts (`--from-profile`)

## Task 1: Create

Ask the user for: Ticker, Position (long/short), Core thesis (falsifiable), 3-5 Buy reasons, 3-5 Assumptions (weighted, with KPI metrics), Sell conditions, Risk factors, optional Target/Stop-loss.

**MCP tools**: `get_company`, `get_financial_metrics`, `get_income_statements(years=3)`

```bash
uv run python $THESIS create {TICKER} --interactive
uv run python $THESIS create {TICKER} --from-profile
uv run python $THESIS create {TICKER} --thesis "Core thesis statement" --position long
uv run python $THESIS create {TICKER} --from-json data.json
```

**Output**: `thesis.json` + empty `updates.json`, `health_checks.json`, `catalysts.json`

## Task 2: Update

Log new data — earnings, news, competitor moves, macro shifts.

Ask for: Event title/description, Assumption impacts (✓/⚠️/✗/—), Strength change, Action (hold/add/trim/exit), Conviction (high/medium/low).

```bash
uv run python $THESIS update {TICKER} --interactive
uv run python $THESIS update {TICKER} --event "Q3 beat" --strength strengthened --action hold --conviction high
```

**Output**: Appended entry in `updates.json`

## Task 3: Health Check

**Composite Score** = Objective × 60% + Subjective × 40% (each 0-100). See `references/scoring-methodology.md`.

- **Objective**: Weighted KPI scores from MCP data
- **Subjective**: LLM qualitative evaluation (CLI uses neutral 50 placeholder)

**MCP tools**: `get_financial_metrics`, `get_income_statements(years=3)`, `get_prices(period="3mo")`

```bash
uv run python $THESIS check {TICKER}
uv run python $THESIS check --all
```

**Output**: Appended entry in `health_checks.json` with per-assumption scorecard

## Task 4: Catalyst Calendar

Track upcoming events; when resolved, trigger Task 2 update flow.

```bash
uv run python $THESIS catalyst {TICKER} --add --event "Q4 Earnings" --date 2026-02-26 --impact positive
uv run python $THESIS catalyst {TICKER} --resolve 1 --outcome "Beat estimates"
uv run python $THESIS catalyst {TICKER} --list
```

**Output**: Entries in `catalysts.json`

## Post-Task

The CLI auto-regenerates `thesis_{TICKER}.md` after every subcommand. Then call MCP `save_analysis_report(ticker, 'thesis_tracker', title, content_md, file_path)` to persist.

## References

| File | Contents |
|------|----------|
| `references/json-schemas.md` | JSON schemas for all thesis artifact files |
| `references/scoring-methodology.md` | Health check scoring methodology |
| `references/quality-checks.md` | Post-task checklists and cross-skill integration |

## Important Notes

- A thesis must be **falsifiable** — if nothing could disprove it, it is not a thesis
- Track disconfirming evidence as rigorously as confirming evidence
- Never overwrite update or health check history — always append
- Review theses at least quarterly
- Domain API lives in `pfs/analysis/thesis_tracker.py`; CLI and Streamlit both use it
```
