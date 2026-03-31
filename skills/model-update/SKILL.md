---
name: model-update
description: Update financial projections when new data arrives — earnings, guidance changes, or revised macro assumptions. Adjusts estimates, recalculates implied valuation, and flags material changes. Triggers on "update model for [ticker]", "plug earnings for [ticker]", "refresh estimates [ticker]", "revise projections [ticker]", or "new guidance [ticker]".
---

# Model Update

Core question: **"Given new data, what are the updated numbers, and does this change the thesis?"**

Adapted from Anthropic's equity-research `model-update` skill. We don't maintain Excel models — instead we keep a `projections.json` per ticker with forward estimates and scenario assumptions, updated when earnings arrive or assumptions change.

## Workflow

### Step 1: Collect Current State (Script)

```bash
uv run python skills/model-update/scripts/collect_model_data.py {TICKER}
```

Fetches:
- Latest annual financials (`GET /api/financials/{TICKER}/annual?years=5`)
- Latest quarterly data (`GET /api/financials/{TICKER}/quarterly?quarters=8`)
- Current metrics (`GET /api/financials/{TICKER}/metrics`)
- Existing projections from `data/artifacts/{TICKER}/model/projections.json` (if any)
- Thesis data from `data/artifacts/{TICKER}/thesis/thesis.json`
- Latest earnings analysis from `data/artifacts/{TICKER}/earnings/`

Writes `model_data_raw.json` to artifacts.

### Step 2: Update Projections (AI)

The agent reviews the collected data and updates forward estimates:

**What changed:**
- New quarterly actuals vs. prior estimates
- Revenue, margins, EPS delta analysis
- Guidance changes (if noted in thesis catalysts)

**Revised estimates:**

| | Old FY Est | New FY Est | Change | Old Next FY | New Next FY | Change |
|---|-----------|-----------|--------|------------|------------|--------|
| Revenue | | | | | | |
| EBITDA | | | | | | |
| EPS | | | | | | |

**Key assumption changes** — what changed and why.

### Step 3: Valuation Impact (AI)

Recalculate implied valuation with updated estimates:
- Forward P/E based on updated EPS
- EV/EBITDA based on updated EBITDA
- Compare to current price → upside/downside

### Step 4: Output

```bash
uv run python skills/model-update/scripts/update_projections.py {TICKER}
uv run python skills/model-update/scripts/update_projections.py {TICKER} --persist
```

## Artifacts

Output goes to `data/artifacts/{TICKER}/model/`:

| File | Contents |
|------|----------|
| `model_data_raw.json` | Collected financials + existing projections |
| `projections.json` | Forward revenue, EPS, margin estimates + scenarios |
| `model_update.md` | Narrative estimate change summary |

### projections.json schema

```json
{
  "schema_version": "1.0",
  "ticker": "NVDA",
  "base_year": 2025,
  "estimates": {
    "FY2026": {"revenue": null, "ebitda": null, "eps": null, "gross_margin": null, "op_margin": null},
    "FY2027": {"revenue": null, "ebitda": null, "eps": null, "gross_margin": null, "op_margin": null}
  },
  "assumptions": {
    "revenue_growth": null,
    "margin_trajectory": "",
    "share_count_trend": "",
    "key_drivers": []
  },
  "valuation": {
    "target_pe": null,
    "target_ev_ebitda": null,
    "implied_price": null,
    "current_price": null,
    "upside_pct": null
  },
  "revision_history": []
}
```

## REST API Endpoints Used

| Endpoint | What we read |
|----------|-------------|
| `GET /api/financials/{TICKER}/annual?years=5` | Historical annual financials |
| `GET /api/financials/{TICKER}/quarterly?quarters=8` | Recent quarterly data |
| `GET /api/financials/{TICKER}/metrics` | Current ratios and margins |
| `GET /api/companies/{TICKER}` | Company details |

## Cross-Skill Reads

- `data/artifacts/{TICKER}/thesis/thesis.json` — thesis assumptions and sell conditions
- `data/artifacts/{TICKER}/earnings/` — latest earnings analysis (actuals vs. estimates)

## Important Notes

- Always reconcile estimates to reported figures before projecting forward
- Note whether estimates are GAAP or adjusted
- Track revision history — it shows analytical progression
- If the quarter was noisy, separate signal from noise
- A model update should trigger a thesis health check if estimates change materially
