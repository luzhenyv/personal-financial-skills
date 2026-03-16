```skill
---
name: thesis-tracker
description: Create, update, and health-check investment theses for portfolio positions and watchlist names. Track catalysts, data points, and thesis milestones over time. Triggers on "create thesis for [ticker]", "update thesis for [ticker]", "thesis health check [ticker]", "is my thesis still intact", "catalyst check [ticker]", or "review my positions".
---

# Thesis Tracker

Maintain and update investment theses for portfolio positions and watchlist names. Core question: **"Is my original buy reason still valid?"**

## Overview

This skill manages investment theses as structured artifacts. Other skills (company-profile, earnings) can feed into it, and the Streamlit dashboard reads from it.

**Data Flow**: `MCP tools / company-profile artifacts → Agent → data/artifacts/{ticker}/thesis/*.json` → `data/artifacts/{ticker}/thesis/thesis_{TICKER}.md` → Streamlit (`http://localhost:8501`)

**Data Source Priority** (fallback chain):
1. **MCP** (PostgreSQL) — most trustworthy, already validated by ETL
2. **Company-profile artifacts** (`data/artifacts/{ticker}/profile/`) — AI-generated analysis
3. **Local SEC filings** (`data/raw/{ticker}/`) — raw 10-K/Q HTML
4. **yfinance** — supplemental price / basic fundamental data
5. **Web search** — last resort for news and qualitative context

**Storage**: All thesis data lives in `data/artifacts/{TICKER}/thesis/` as JSON files + a generated markdown report. The agent **never writes to PostgreSQL** — it reads financial data through MCP tools and writes artifacts to the filesystem only. Reports are persisted to the `analysis_reports` table via MCP `save_analysis_report`.

## Trigger

- "create thesis for {ticker}" / "new thesis for {ticker}"
- "update thesis for {ticker}" / "add data point to {ticker} thesis"
- "thesis health check {ticker}" / "is my thesis still intact" / "thesis check {ticker}"
- "add catalyst for {ticker}" / "catalyst check {ticker}"
- "review my positions" (batch health check)

## Prerequisite: Company Data

Before creating a thesis, verify financial data is available:

1. Call MCP `list_companies` — confirm the ticker appears
2. Call MCP `get_company(ticker)` — confirm basic company data exists

If the ticker is **not** in the database, instruct the user to run ETL first:
```bash
uv run python -m src.etl.pipeline ingest {TICKER} --years 5
```

**Optional enrichment**: If `data/artifacts/{TICKER}/profile/investment_thesis.json` exists (from company-profile skill), use it to seed buy reasons and risks.

## Task Overview

| Task | Name | Prerequisites | Output |
|------|------|--------------|--------|
| **1** | Thesis Creation | Ticker + position rationale | `thesis.json` + `thesis_{TICKER}.md` |
| **2** | Thesis Update | Existing thesis + new data point | Appended entry in `updates.json` |
| **3** | Thesis Health Check | Existing thesis + MCP financials | Score entry in `health_checks.json` |
| **4** | Catalyst Calendar | Existing thesis | `catalysts.json` entries |

**Default mode**: Run the requested task. After any task, regenerate `thesis_{TICKER}.md` and call MCP `save_analysis_report` to persist.

---

## Task 1: Thesis Creation

Define a new investment thesis. If `data/artifacts/{TICKER}/profile/investment_thesis.json` exists, offer to seed bull case / buy reasons from it. If `risk_factors.json` exists, offer to seed "where I might be wrong".

**Ask the user for**:
- **Ticker** and **Position** (Long / Short)
- **Core thesis** (1-2 sentence statement — must be falsifiable)
- **3-5 Buy reasons** (specific, evidence-based arguments)
- **3-5 Prerequisite assumptions** (falsifiable, with weights summing to 100%, each with a KPI metric)
- **Sell conditions** (specific, actionable triggers)
- **Where I might be wrong** (genuine bear case arguments)
- **Target price** and **Stop-loss** (optional)

**MCP tools to use**:
- `get_company(ticker)` — company metadata
- `get_financial_metrics(ticker)` — current ratios for assumption KPI baselines
- `get_income_statements(ticker, years=3)` — recent earnings trajectory

**Output**: `data/artifacts/{TICKER}/thesis/thesis.json` + initialized empty `updates.json`, `health_checks.json`, `catalysts.json`.

```bash
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} \
    --position long --thesis "Core thesis statement here"
# Seed from company-profile artifacts:
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} --from-profile
# Interactive mode:
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} --interactive
```

---

## Task 2: Thesis Update

Log new information — earnings, news, competitor moves, management changes, macro shifts.

**Ask the user for**:
- **Trigger event** (what happened)
- **Assumption impacts** (✓ strengthened / ⚠️ weakened / ✗ broken / — no change, per assumption)
- **Thesis strength change** (Strengthened / Weakened / Unchanged)
- **Action** (Hold / Add / Trim / Exit)
- **Conviction** (High / Medium / Low)
- **Notes** (optional context)

**Output**: Appended entry in `data/artifacts/{TICKER}/thesis/updates.json`.

```bash
uv run python skills/thesis-tracker/scripts/update_thesis.py {TICKER} \
    --event "Q3 2025 earnings beat" --strength strengthened --action hold --conviction high
# Interactive mode:
uv run python skills/thesis-tracker/scripts/update_thesis.py {TICKER} --interactive
```

---

## Task 3: Thesis Health Check

Evaluate whether original buy reasons are still valid. Compute **Composite Score** = (Objective × 60%) + (Subjective × 40%), each 0–100. See `references/scoring-methodology.md` for full methodology.

- **Objective**: Weighted average of per-assumption KPI scores from MCP financial data
- **Subjective**: LLM evaluation of qualitative factors with specific event references

**MCP tools to use**:
- `get_financial_metrics(ticker)` — latest ratios for KPI scoring
- `get_income_statements(ticker, years=3)` — earnings trajectory
- `get_prices(ticker, period="3mo")` — recent price action

**Output**: Appended entry in `data/artifacts/{TICKER}/thesis/health_checks.json` with assumption scorecard.

```bash
uv run python skills/thesis-tracker/scripts/health_check.py {TICKER}
# Batch check all active theses:
uv run python skills/thesis-tracker/scripts/health_check.py --all
```

---

## Task 4: Catalyst Calendar

Track upcoming events that could prove or disprove the thesis.

**Ask the user for**:
- **Event** (earnings, product launch, regulatory decision, etc.)
- **Expected date**
- **Expected impact** (which assumption it affects, positive / negative / neutral)
- **Notes**

When a catalyst materializes, mark it as resolved and trigger the update flow (Task 2).

**Output**: `data/artifacts/{TICKER}/thesis/catalysts.json` entries.

```bash
uv run python skills/thesis-tracker/scripts/manage_catalysts.py {TICKER} --add
uv run python skills/thesis-tracker/scripts/manage_catalysts.py {TICKER} --resolve 1
uv run python skills/thesis-tracker/scripts/manage_catalysts.py {TICKER} --list
```

---

## Post-Task: Report Generation

After any task (create, update, health check, catalyst change), regenerate the markdown report:

```bash
uv run python skills/thesis-tracker/scripts/generate_report.py {TICKER}
```

Then call MCP `save_analysis_report(ticker, 'thesis_tracker', title, content_md, file_path)` to persist the report in the database.

**Output**: `data/artifacts/{TICKER}/thesis/thesis_{TICKER}.md`, viewable in Streamlit.

---

## Quick Reference

```bash
# Prerequisite: ensure ETL has ingested the ticker
uv run python -m src.etl.pipeline ingest {TICKER} --years 5

# Task 1: Create thesis
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} --interactive
# Task 2: Log an update
uv run python skills/thesis-tracker/scripts/update_thesis.py {TICKER} --interactive
# Task 3: Run health check
uv run python skills/thesis-tracker/scripts/health_check.py {TICKER}
# Task 4: Manage catalysts
uv run python skills/thesis-tracker/scripts/manage_catalysts.py {TICKER} --add
# Regenerate report (run after any task)
uv run python skills/thesis-tracker/scripts/generate_report.py {TICKER}
```

## References

| File | Contents |
|------|----------|
| `references/json-schemas.md` | JSON schemas for thesis.json, updates.json, health_checks.json, catalysts.json |
| `references/scoring-methodology.md` | Health check scoring: objective KPI rules, subjective evaluation criteria, data sources |
| `references/quality-checks.md` | Post-task quality checklists, cross-skill integration, Streamlit integration |

## Important Notes

- A thesis must be **falsifiable** — if nothing could disprove it, it is not a thesis
- Track disconfirming evidence as rigorously as confirming evidence
- Never overwrite update or health check history — always append
- Review theses at least quarterly, even when nothing dramatic has happened
- If the user manages multiple positions, offer to do a full portfolio thesis review
- The markdown file is the human-readable record; JSON files are the structured store
```
