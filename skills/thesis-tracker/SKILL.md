```skill
---
name: thesis-tracker
description: Create, update, and health-check investment theses for portfolio positions and watchlist names. Core question — "Is my buy reason still valid?" Triggers on "create thesis for [ticker]", "update thesis for [ticker]", "thesis health check [ticker]", "is my thesis still intact", "review my positions". Stores structured data in PostgreSQL and thesis markdown in data/artifacts/{ticker}/.
---

# Thesis Tracker

Personal investment thesis management — the system of record that answers:
**"Is my original buy reason still valid?"**

## Overview

This skill is the **core state management layer** for the entire investment workflow. Other skills (company-profile, earnings, catalysts) write into it, and the Streamlit dashboard reads from it.

**Data Flow**: `company-profile → thesis creation → PostgreSQL + thesis_{ticker}.md` → updates/health checks → DB + Streamlit

**Storage**: PostgreSQL tables (`investment_theses`, `thesis_updates`, `thesis_health_checks`) + `data/artifacts/{TICKER}/thesis_{TICKER}.md` + Streamlit at `http://localhost:8501`

## Trigger

- "create thesis for {ticker}" / "update thesis for {ticker}"
- "thesis health check {ticker}" / "is my thesis still intact" / "thesis check {ticker}"
- "add data point to {ticker} thesis" / "review my positions" (batch)

## Tasks

| Task | Name | Prerequisites | Output |
|------|------|--------------|--------|
| **1** | Thesis Creation | Ticker + position rationale | `thesis_{TICKER}.md` + DB row |
| **2** | Thesis Update | Existing thesis + new data point | Appended log entry + DB row |
| **3** | Thesis Health Check | Existing thesis + latest financials | Health score + DB row |

---

## Task 1: Thesis Creation

Triggered when establishing a position or researching a stock. If `data/artifacts/{TICKER}/investment_thesis.json` exists (from company-profile), use it to seed bull case / risks.

**Ask the user for**: Ticker, Position (Long/Short), Core thesis (1-2 sentences), 3 Buy reasons, 3-5 Prerequisite assumptions (falsifiable, with weights), Sell conditions, Where I might be wrong.

**Output**: Generate `data/artifacts/{TICKER}/thesis_{TICKER}.md` (see `references/output-templates.md`) + insert row into `investment_theses` table (see `references/database-schema.md`).

```bash
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} \
    --position long --thesis "Core thesis statement here"
# Interactive mode:
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} --interactive
```

---

## Task 2: Thesis Update

Triggered by new information — earnings, news, competitor moves, management changes, macro shifts.

**Ask the user for**: Ticker, Trigger event, Assumption impacts (✓/⚠️/—), Thesis strength change (Strengthened/Weakened/Unchanged), Action (Hold/Add/Trim/Exit), Conviction (High/Medium/Low), Notes.

**Output**: Append update entry to thesis markdown (see `references/output-templates.md`) + insert row into `thesis_updates` table.

```bash
uv run python skills/thesis-tracker/scripts/update_thesis.py {TICKER} \
    --event "Q3 2025 earnings beat" --strength strengthened --action hold --conviction high
# Interactive mode:
uv run python skills/thesis-tracker/scripts/update_thesis.py {TICKER} --interactive
```

---

## Task 3: Thesis Health Check

Evaluates whether original buy reasons are still valid. Computes **Composite Score** = (Objective × 60%) + (Subjective × 40%), each 0–100. See `references/scoring-methodology.md` for full methodology.

- **Objective**: Weighted average of per-assumption KPI scores from financial data
- **Subjective**: LLM evaluation of qualitative factors with specific event references

**Output**: Append health check scorecard to thesis markdown (see `references/output-templates.md`) + insert row into `thesis_health_checks` table.

```bash
uv run python skills/thesis-tracker/scripts/health_check.py {TICKER}
# Batch check all active theses:
uv run python skills/thesis-tracker/scripts/health_check.py --all
```

---

## References

| File | Contents |
|------|----------|
| `references/database-schema.md` | Full PostgreSQL table schemas (investment_theses, thesis_updates, thesis_health_checks) |
| `references/output-templates.md` | Markdown templates for thesis creation, updates, and health checks |
| `references/scoring-methodology.md` | Health check scoring: objective KPI rules, subjective evaluation criteria, data sources |
| `references/quality-checks.md` | Post-task quality checklists, Streamlit integration, cross-skill integration notes |

---

## Important Notes

- A thesis must be **falsifiable** — if nothing could disprove it, it is not a thesis
- Track disconfirming evidence as rigorously as confirming evidence
- The markdown file is the human-readable record; PostgreSQL is the queryable store
- Never overwrite thesis update history — always append
- Review theses at least quarterly, even when nothing dramatic has happened
- The default objective/subjective weight split (60/40) can be overridden per-thesis
```
