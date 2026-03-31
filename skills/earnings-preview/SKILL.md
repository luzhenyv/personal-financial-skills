---
name: earnings-preview
description: Pre-earnings scenario analysis — consensus estimates, bull/base/bear scenarios, key metrics to watch, and catalyst checklist. Triggers on "earnings preview for [ticker]", "preview Q[X] for [ticker]", "what to watch for [ticker] earnings", or "pre-earnings [ticker]".
---

# Earnings Preview

Core question: **"What should I expect, what should I watch, and how does each outcome affect my thesis?"**

Adapted from Anthropic's equity-research `earnings-preview` skill, simplified for our single-analyst scale with thesis-tracker integration.

## Workflow

### Step 1: Gather Context (Script)

Collect recent financial data and thesis context from the REST API:

```bash
uv run python skills/earnings-preview/scripts/collect_preview.py {TICKER}
uv run python skills/earnings-preview/scripts/collect_preview.py {TICKER} --quarter Q1 --year 2026
```

This fetches:
- Last 8 quarters of financials (`GET /api/financials/{TICKER}/quarterly?quarters=8`)
- Latest metrics and margins (`GET /api/financials/{TICKER}/metrics`)
- Segment breakdown (`GET /api/financials/{TICKER}/segments`)
- Recent price action (`GET /api/financials/{TICKER}/prices?period=3mo`)
- Existing thesis data from `data/artifacts/{TICKER}/thesis/thesis.json`
- Latest catalyst calendar from `data/artifacts/{TICKER}/thesis/catalysts.json`

Writes `preview_{Q}_{YEAR}_raw.json` to artifacts.

### Step 2: Scenario Framework (AI)

The agent reads the raw data and produces:

**Consensus & Recent Trends:**
- Revenue, EPS, margin trends from last 4-8 quarters
- Sequential and year-over-year growth rates
- Management guidance from prior quarter (if available in thesis catalysts)

**Bull / Base / Bear Scenarios:**

| Scenario | Revenue | EPS | Key Driver | Expected Stock Reaction |
|----------|---------|-----|------------|------------------------|
| Bull | | | | |
| Base | | | | |
| Bear | | | | |

For each scenario: what would need to happen operationally, and how it maps to thesis assumptions.

### Step 3: Key Metrics & Catalyst Checklist (AI)

Identify the 3-5 things that will determine the stock's reaction:

1. **[Metric]** vs. trend — why it matters for the thesis
2. **[Guidance item]** — what continuation/change would signal
3. **[Narrative shift]** — strategic changes that could move the stock

### Step 4: Output

```bash
uv run python skills/earnings-preview/scripts/generate_preview.py {TICKER}
uv run python skills/earnings-preview/scripts/generate_preview.py {TICKER} --persist
```

## Artifacts

Output goes to `data/artifacts/{TICKER}/earnings/`:

| File | Contents |
|------|----------|
| `preview_{Q}_{YEAR}_raw.json` | Collected data for AI analysis |
| `preview_{Q}_{YEAR}.json` | Structured scenario framework |
| `preview_{Q}_{YEAR}.md` | Narrative earnings preview |

## REST API Endpoints Used

| Endpoint | What we read |
|----------|-------------|
| `GET /api/financials/{TICKER}/quarterly?quarters=8` | Quarterly trend data |
| `GET /api/financials/{TICKER}/metrics` | Current margins and ratios |
| `GET /api/financials/{TICKER}/segments` | Segment breakdown |
| `GET /api/financials/{TICKER}/prices?period=3mo` | Recent price action |
| `GET /api/companies/{TICKER}` | Company details (sector, industry) |

## Cross-Skill Reads

- `data/artifacts/{TICKER}/thesis/thesis.json` — thesis assumptions to map scenarios against
- `data/artifacts/{TICKER}/thesis/catalysts.json` — upcoming catalysts and prior guidance

## Important Notes

- Always note that estimates are based on historical trends, not consensus — we don't have sell-side consensus data
- Historical earnings reactions help calibrate expectations
- The preview should be created 3-5 days before expected earnings
- If a thesis exists, every scenario must reference its impact on thesis assumptions
