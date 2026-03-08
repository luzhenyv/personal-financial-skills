```skill
---
name: thesis-tracker
description: Create, update, and health-check investment theses for portfolio positions and watchlist names. Core question — "Is my buy reason still valid?" Triggers on "create thesis for [ticker]", "update thesis for [ticker]", "thesis health check [ticker]", "is my thesis still intact", "review my positions". Stores structured data in PostgreSQL and thesis markdown in data/processed/{ticker}/.
---

# Thesis Tracker

Personal investment thesis management — the system of record that answers:
**"Is my original buy reason still valid?"**

## Overview

This skill is the **core state management layer** for the entire investment workflow. It does not operate in isolation — other skills (company-profile, earnings, catalysts) write into it, and the Streamlit dashboard reads from it.

**Data Flow**:
```
company-profile → initial thesis creation → PostgreSQL + thesis_{ticker}.md
earnings / catalysts (future) → thesis updates → append log + DB insert
health check (manual / periodic) → evaluation → DB insert → Streamlit chart
```

**Storage**:
- Structured data: PostgreSQL tables (`investment_theses`, `thesis_updates`, `thesis_health_checks`)
- Human-readable file: `data/processed/{TICKER}/thesis_{TICKER}.md`
- Streamlit visualization: `http://localhost:8501` → Thesis Tracker page

## Trigger

- "create thesis for {ticker}"
- "update thesis for {ticker}"
- "thesis health check {ticker}" or "is my thesis still intact"
- "thesis check {ticker}"
- "add data point to {ticker} thesis"
- "review my positions" (batch health check)

## Task Overview

| Task | Name | Prerequisites | Output |
|------|------|--------------|--------|
| **1** | Thesis Creation | Ticker + position rationale | `thesis_{TICKER}.md` + DB row |
| **2** | Thesis Update | Existing thesis + new data point | Appended log entry + DB row |
| **3** | Thesis Health Check | Existing thesis + latest financials | Health score + DB row |

---

## Task 1: Thesis Creation

Triggered when the user first establishes a position or begins researching a stock. If `data/processed/{TICKER}/investment_thesis.json` exists (from the company-profile skill), use it as the starting point for bull case / risks.

### Inputs

Ask the user for:
- **Ticker**: Company ticker symbol
- **Position**: Long or Short
- **Core thesis**: 1-2 sentence summary of why they own / are watching it
- **Buy reasons**: 3 key reasons (can seed from `investment_thesis.json` bull_case)
- **Prerequisite assumptions**: 3-5 falsifiable assumptions that MUST hold for the thesis to work
- **Sell conditions**: What would make them exit
- **Where I might be wrong**: Honest self-assessment of the biggest risks to the thesis

### Output

Generate `data/processed/{TICKER}/thesis_{TICKER}.md`:

```markdown
# {TICKER} Investment Thesis
**Created:** {date}
**Status:** Active
**Position:** Long

## Core Thesis
{One-sentence thesis statement}

## Buy Reasons
1. {Reason 1}
2. {Reason 2}
3. {Reason 3}

## Prerequisite Assumptions
- Assumption 1: {description} [Weight: X%]
- Assumption 2: {description} [Weight: Y%]
- Assumption 3: {description} [Weight: Z%]

## Sell Conditions
- {Condition 1}
- {Condition 2}
- {Condition 3}

## Where I Might Be Wrong
- {Risk 1}
- {Risk 2}
- {Risk 3}

## Thesis Update Log
(Updates will be appended below)
```

Also insert a row into `investment_theses` table (see schema below).

### Script

```bash
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} \
    --position long \
    --thesis "Core thesis statement here"
# Interactive mode (prompts for all fields):
uv run python skills/thesis-tracker/scripts/create_thesis.py {TICKER} --interactive
```

---

## Task 2: Thesis Update

Triggered by new information — earnings results, major news, competitor moves, management changes, macro shifts. This is the primary integration point with future `earnings` and `catalysts` skills.

### Inputs

- **Ticker**: Which thesis to update
- **Trigger event**: What happened (e.g., "Q3 earnings: revenue beat by 15%")
- **Assumption impacts**: For each prerequisite assumption, has this event strengthened (✓), weakened (⚠️), or not affected (—) it?
- **Thesis strength change**: Strengthened / Weakened / Unchanged
- **Action**: No change / Increase position / Trim / Exit
- **Updated conviction**: High / Medium / Low
- **Notes**: Any additional context

### Output

**Append** to `data/processed/{TICKER}/thesis_{TICKER}.md`:

```markdown
### {date} | {event_title}
**Trigger:** {what happened}
**Assumption Changes:**
- Assumption 1: {status_emoji} — {brief explanation}
- Assumption 2: {status_emoji} — {brief explanation}
- Assumption 3: {status_emoji} — {brief explanation}

**Thesis Strength:** {Strengthened/Weakened/Unchanged}
**Action:** {action taken}
**Conviction:** {High/Medium/Low}
```

Also insert a row into `thesis_updates` table.

<!-- PLACEHOLDER: earnings skill integration
When the earnings skill is built, it will automatically call thesis update
after processing quarterly results. The earnings skill will:
1. Compare actual results against thesis assumptions
2. Auto-populate assumption impact assessments
3. Prompt the user for action decision
-->

<!-- PLACEHOLDER: catalysts skill integration
When the catalysts skill is built, it will trigger thesis updates when
tracked catalysts materialize. The catalysts skill will:
1. Monitor a calendar of thesis-relevant events
2. When a catalyst occurs, create a thesis update entry
3. Flag assumption changes based on catalyst outcome
-->

### Script

```bash
uv run python skills/thesis-tracker/scripts/update_thesis.py {TICKER} \
    --event "Q3 2025 earnings beat" \
    --strength strengthened \
    --action hold \
    --conviction high
# Interactive mode:
uv run python skills/thesis-tracker/scripts/update_thesis.py {TICKER} --interactive
```

---

## Task 3: Thesis Health Check

The highest-value function. Evaluates whether the original buy reasons are still valid by computing both an **objective score** (from quantitative financial data) and a **subjective score** (from LLM judgment on qualitative factors).

### Scoring Methodology

**Composite Score** = (Objective Score × 60%) + (Subjective Score × 40%)

Each score is 0–100. The breakdown is always visible alongside the composite.

#### Objective Score (60% weight)

Computed from quantitative data changes since thesis creation or last check. For each prerequisite assumption, define measurable KPIs:

| Example Assumption | KPI | Scoring Rule |
|---|---|---|
| "Gross margin stays above 60%" | Latest gross margin | >65%: 100, 60-65%: 75, 55-60%: 40, <55%: 10 |
| "Revenue growth >20% YoY" | TTM revenue growth | >25%: 100, 20-25%: 80, 15-20%: 50, <15%: 20 |
| "No credible competitive threat" | Market share trend | Stable/growing: 90, slight decline: 60, major decline: 20 |

The objective score is the weighted average of per-assumption KPI scores, using the weights defined at thesis creation.

Data sources:
- PostgreSQL tables: `income_statements`, `balance_sheets`, `financial_metrics`
- Latest price data: `daily_prices`
- Processed JSON: `data/processed/{TICKER}/*.json`

#### Subjective Score (40% weight)

LLM evaluates qualitative factors that are hard to quantify:
- Competitive dynamics (new entrants, technology shifts)
- Management quality and capital allocation decisions
- Regulatory and geopolitical risks
- Narrative / sentiment shifts in the market
- Whether the original thesis "story" still makes sense

The LLM should reference specific recent events, not just give a generic assessment. The subjective score must include a brief justification (2-3 sentences) for each assumption rating.

### Output

**Append** to `data/processed/{TICKER}/thesis_{TICKER}.md`:

```markdown
## Thesis Health Check | {date}

### Assumption Scorecard
| Assumption | Weight | Objective | Subjective | Combined | Status |
|------------|--------|-----------|------------|----------|--------|
| {Assumption 1} | 40% | 85 | 80 | 83 | ✓ Intact |
| {Assumption 2} | 35% | 70 | 65 | 68 | ⚠️ Watch |
| {Assumption 3} | 25% | 90 | 85 | 88 | ✓ Intact |

### Composite Score: 80/100 (prev: 91/100)
- Objective: 82/100
- Subjective: 77/100

### Key Observations
- {What strengthened}
- {What weakened}
- {What to monitor}

### Recommendation
{Hold / Trim / Add / Exit — with reasoning}
```

Also insert a row into `thesis_health_checks` table.

### Script

```bash
uv run python skills/thesis-tracker/scripts/health_check.py {TICKER}
# Batch check all active theses:
uv run python skills/thesis-tracker/scripts/health_check.py --all
```

---

## Database Schema

Three new PostgreSQL tables. See `src/db/schema.sql` for full DDL.

### investment_theses
Core thesis record — one row per ticker.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| ticker | VARCHAR(10) FK | References companies.ticker |
| position | VARCHAR(10) | 'long' or 'short' |
| status | VARCHAR(20) | 'active', 'watching', 'closed' |
| core_thesis | TEXT | 1-2 sentence thesis statement |
| buy_reasons | JSONB | Array of reason objects |
| assumptions | JSONB | Array of {description, weight, kpi_metric, kpi_thresholds} |
| sell_conditions | JSONB | Array of condition strings |
| risk_factors | JSONB | Array of "where I might be wrong" items |
| target_price | NUMERIC(12,4) | Optional target price |
| stop_loss_price | NUMERIC(12,4) | Optional stop-loss trigger |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |
| closed_at | TIMESTAMP | When thesis was closed |
| close_reason | TEXT | Why the thesis was closed |

### thesis_updates
Append-only log of thesis-affecting events.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| ticker | VARCHAR(10) FK | |
| event_date | DATE | When the event happened |
| event_title | VARCHAR(255) | Short label |
| event_description | TEXT | What occurred |
| assumption_impacts | JSONB | {assumption_idx: {status, explanation}} |
| strength_change | VARCHAR(20) | 'strengthened', 'weakened', 'unchanged' |
| action_taken | VARCHAR(20) | 'hold', 'add', 'trim', 'exit' |
| conviction | VARCHAR(10) | 'high', 'medium', 'low' |
| notes | TEXT | |
| source | VARCHAR(50) | 'manual', 'earnings', 'catalyst' |
| created_at | TIMESTAMP | |

### thesis_health_checks
Point-in-time thesis evaluation snapshots.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| ticker | VARCHAR(10) FK | |
| check_date | DATE | |
| objective_score | NUMERIC(5,2) | 0-100, from quantitative KPIs |
| subjective_score | NUMERIC(5,2) | 0-100, from LLM judgment |
| composite_score | NUMERIC(5,2) | Weighted: 60% obj + 40% subj |
| assumption_scores | JSONB | Per-assumption breakdown |
| key_observations | JSONB | Array of observation strings |
| recommendation | VARCHAR(20) | 'hold', 'add', 'trim', 'exit' |
| recommendation_reasoning | TEXT | |
| created_at | TIMESTAMP | |

---

## Streamlit Integration

The Thesis Tracker Streamlit page (`streamlit_app/pages/2_thesis_tracker.py`) provides:

1. **Active Theses Overview** — Table of all active theses with latest conviction and composite score
2. **Thesis Detail View** — Full thesis + update log + health history for a selected ticker
3. **Health Score Timeline** — Plotly line chart showing composite, objective, and subjective scores over time
4. **Assumption Heatmap** — Per-assumption score trends across health checks
5. **Update Timeline** — Chronological log of all thesis updates with strength indicators

---

## Integration with Other Skills

### company-profile (existing)
- On thesis creation, reads `investment_thesis.json` to seed bull case / buy reasons
- On thesis creation, reads `competitive_landscape.json` and `risk_factors.json` to seed assumptions and risks

### earnings (future — placeholder)
- After earnings processing, automatically creates a thesis update entry
- Compares actual results against thesis assumption KPIs
- Prompts user for action decision

### catalysts (future — placeholder)
- Maintains a calendar of thesis-relevant upcoming events
- When a catalyst materializes, triggers thesis update flow
- Tracks catalyst outcomes (confirmed / missed / delayed)

---

## Quality Checks

After thesis creation:
- [ ] All 3+ buy reasons have specific, falsifiable claims
- [ ] All assumptions have measurable KPIs and explicit weights summing to 100%
- [ ] Sell conditions are specific enough to be actionable
- [ ] "Where I might be wrong" contains genuine bear case arguments

After thesis update:
- [ ] Every assumption has an explicit status (✓ / ⚠️ / ✗ / —)
- [ ] Action taken is recorded (even if "no change")
- [ ] Both DB row and markdown file are updated

After health check:
- [ ] Objective score pulls from latest financial data (not stale)
- [ ] Subjective score includes specific event references
- [ ] Score breakdown totals correctly (weights sum to 100%)
- [ ] Previous score shown for comparison

---

## Important Notes

- A thesis must be **falsifiable** — if nothing could disprove it, it is not a thesis
- Track disconfirming evidence as rigorously as confirming evidence
- The markdown file is the human-readable record; PostgreSQL is the queryable store
- Never overwrite thesis update history — always append
- Review theses at least quarterly, even when nothing dramatic has happened
- If the user manages multiple positions, offer batch health check (`--all`)
- The default objective/subjective weight split (60/40) can be overridden per-thesis if needed
```
