---
name: thesis-tracker
description: Maintain and update investment theses for portfolio positions and watchlist names. Track key data points, catalysts, and thesis milestones over time. Triggers on "create thesis for [ticker]", "update thesis for [ticker]", "thesis health check [ticker]", "is my thesis still intact", "add catalyst for [ticker]", or "review my positions".
---

# Thesis Tracker

Core question: **"Is my original buy reason still valid?"**

## Workflow

### Step 1: Define or Load Thesis

If creating a new thesis:
- **Company**: Ticker (must exist in REST API — `GET /api/companies/{TICKER}`)
- **Position**: Long or Short
- **Thesis statement**: 1-2 sentence core thesis — must be falsifiable
- **Key pillars**: 3-5 buy reasons with title and description
- **Assumptions**: 3-5 weighted assumptions with KPI metrics and thresholds (weights must sum to 100%)
- **Sell conditions**: Specific, actionable exit triggers
- **Key risks**: 3-5 risks that would invalidate the thesis
- **Target price / Stop-loss**: Optional price targets

If `GET /api/companies/{TICKER}` returns 404, tell the user:

> I don't have financial data for {TICKER} yet. Please run ETL first:
> ```bash
> uv run python -m pfs.etl.pipeline ingest {TICKER} --years 5
> ```
> This will pull SEC filings, financial statements, and price history. Once done, I can create the thesis.

Do **not** run ETL yourself — that belongs to the Data Plane.

Optionally seed from company-profile artifacts (`--from-profile`).

```bash
uv run python skills/thesis-tracker/scripts/thesis_cli.py create {TICKER} --interactive
```

### Step 2: Update Log

For each new data point or development (earnings, news, competitor moves, macro shifts):
- **Event**: What happened and when
- **Assumption impacts**: Score each assumption (✓ strengthened / ⚠️ weakened / ✗ broken / — no change)
- **Thesis strength**: Strengthened / Weakened / Unchanged
- **Action**: Hold / Add / Trim / Exit
- **Conviction**: High / Medium / Low

```bash
uv run python skills/thesis-tracker/scripts/thesis_cli.py update {TICKER} --interactive
```

### Step 3: Health Check

Composite Score = Objective (60%) + Subjective (40%), each 0-100.

- **Objective**: Weighted KPI scores from REST API financial data
- **Subjective**: Agent qualitative evaluation (see `references/health-check-prompt.md`)

Recommendation: ≥75 Hold (strong) · 50-74 Hold (cautious) · 30-49 Trim · <30 Exit

See `references/scoring-methodology.md` for full methodology.

```bash
uv run python skills/thesis-tracker/scripts/thesis_cli.py check {TICKER}
```

### Step 4: Catalyst Calendar

Track upcoming events that could prove or disprove the thesis:

| Field | Description |
|-------|-------------|
| Event | What's happening |
| Date | When it's expected |
| Impact | Positive / Negative / Neutral |

```bash
uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst {TICKER} --add
uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst {TICKER} --list
uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst {TICKER} --resolve 1
```

### Step 5: Output

All artifacts go to `data/artifacts/{TICKER}/thesis/`:

| File | Contents |
|------|----------|
| `thesis.json` | Core thesis record |
| `updates.json` | Append-only event log |
| `health_checks.json` | Health check history |
| `catalysts.json` | Catalyst calendar |
| `thesis_{TICKER}.md` | Generated markdown report |

The CLI auto-regenerates the markdown report after every subcommand. Persist via `POST /api/analysis/reports`.

## References

| File | Contents |
|------|----------|
| `references/json-schemas.md` | JSON schemas for all artifact files |
| `references/scoring-methodology.md` | Health check scoring methodology |
| `references/health-check-prompt.md` | Structured prompt for agent subjective scoring |
| `references/quality-checks.md` | Post-task checklists |

## Important Notes

- A thesis must be **falsifiable** — if nothing could disprove it, it's not a thesis
- Track disconfirming evidence as rigorously as confirming evidence
- Never overwrite update or health check history — always append
- Review theses at least quarterly
- Assumption weights must sum to 100% (auto-normalized if they don't)
```
